"""
NISAR GCOV starter for the Black Sea ship-monitoring idea.

Commands:
  python nisar_blacksea.py search  [bbox] [start] [end]     # no login needed (NASA CMR)
  python nisar_blacksea.py inspect <granule_url>            # print HDF5 tree (needs Earthdata login)
  python nisar_blacksea.py ships   <granule_url> [bbox]     # crop + CFAR ship detection -> CSV + PNG

Setup:
  pip install earthaccess h5py numpy scipy matplotlib pyproj
  Earthdata login: https://urs.earthdata.nasa.gov  -> earthaccess.login() will prompt / use ~/.netrc

bbox = "minlon,minlat,maxlon,maxlat" (WGS84). Default: western Black Sea shelf
(Bosporus -> Bulgaria -> Romania -> Odesa), the best-covered part of the sea.
"""
import json
import sys
import urllib.request

DEFAULT_BBOX = "27.4,41.0,31.5,46.8"
COLLECTIONS = ["NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1"]  # validated (>=2026-10-21), provisional (Jun-Oct 2026)
GRID = "/science/LSAR/GCOV/grids/frequencyA"


def search(bbox=DEFAULT_BBOX, start="2026-06-01", end="2026-12-31"):
    out = []
    for sn in COLLECTIONS:
        url = (f"https://cmr.earthdata.nasa.gov/search/granules.json?short_name={sn}"
               f"&bounding_box={bbox}&temporal={start}T00:00:00Z,{end}T23:59:59Z&page_size=2000")
        for g in json.load(urllib.request.urlopen(url, timeout=120))["feed"]["entry"]:
            h5 = [l["href"] for l in g["links"] if l["href"].startswith("https") and l["href"].endswith(".h5")]
            png = [l["href"] for l in g["links"] if l["href"].startswith("https") and l["href"].endswith(".png")]
            out.append(dict(title=g["title"], start=g["time_start"], size_mb=float(g.get("granule_size", 0)),
                            h5=h5[0] if h5 else None, browse=png[0] if png else None))
    out.sort(key=lambda r: r["start"])
    for r in out:
        print(f'{r["start"][:16]}  {r["size_mb"]:7.0f} MB  {r["title"]}')
    print(f"\n{len(out)} granules. Browse PNGs are public (no login): field 'browse'.")
    json.dump(out, open("granules.json", "w"), indent=1)
    print("saved granules.json")
    return out


def _open(url):
    import earthaccess
    import h5py
    earthaccess.login()
    fs = earthaccess.get_fsspec_https_session()
    # streams only the chunks we touch -> no need to download the ~2 GB file
    return h5py.File(fs.open(url, block_size=8 * 1024 * 1024), "r")


def inspect(url):
    f = _open(url)
    f.visititems(lambda n, o: print(n, getattr(o, "shape", ""), getattr(o, "dtype", "")))


def ships(url, bbox=DEFAULT_BBOX, pol="HVHV", pfa_k=5.0):
    import numpy as np
    from pyproj import Transformer
    from scipy import ndimage
    f = _open(url)
    g = f[GRID]
    x, y = g["xCoordinates"][:], g["yCoordinates"][:]          # UTM metres (verify names with `inspect`)
    epsg = int(g["projection"].attrs.get("epsg_code", g["projection"][()]))
    lon0, lat0, lon1, lat1 = map(float, bbox.split(","))
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    ci = np.where((x >= min(xs)) & (x <= max(xs)))[0]
    ri = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    if not len(ci) or not len(ri):
        sys.exit("bbox does not overlap this granule")
    sl = (slice(ri.min(), ri.max() + 1), slice(ci.min(), ci.max() + 1))
    img = g[pol][sl].astype("float32")                          # gamma0, linear power
    img[~np.isfinite(img)] = np.nan

    # Simple CA-CFAR: pixel >> local sea clutter. HV is best for ships (sea is dark in cross-pol).
    valid = np.isfinite(img)
    a = np.where(valid, img, 0)
    win, guard = 41, 9
    s_big = ndimage.uniform_filter(a, win) * win**2 - ndimage.uniform_filter(a, guard) * guard**2
    n_big = ndimage.uniform_filter(valid.astype("f4"), win) * win**2 - ndimage.uniform_filter(valid.astype("f4"), guard) * guard**2
    s2 = ndimage.uniform_filter(a**2, win) * win**2 - ndimage.uniform_filter(a**2, guard) * guard**2
    mu = s_big / np.maximum(n_big, 1)
    sd = np.sqrt(np.maximum(s2 / np.maximum(n_big, 1) - mu**2, 0))
    det = valid & (img > mu + pfa_k * sd) & (img > 3 * mu)
    # NOTE: land / coast / wind farms / platforms also fire. Mask land with a coastline shapefile
    # (e.g. Natural Earth / OSM land polygons, buffered ~500 m) before trusting results.
    lab, n = ndimage.label(det)
    objs = ndimage.find_objects(lab)
    to_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
    rows = []
    for i, o in enumerate(objs, 1):
        npx = int((lab[o] == i).sum())
        if npx < 2 or npx > 400:   # drop speckle + big land blobs
            continue
        r, c = ndimage.center_of_mass(lab == i)
        lon, lat = to_ll.transform(x[sl[1]][int(c)], y[sl[0]][int(r)])
        rows.append((lon, lat, npx, float(np.nanmax(img[o]))))
    import csv
    with open("detections.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["lon", "lat", "n_pixels", "peak_gamma0"]); w.writerows(rows)
    print(f"{len(rows)} candidate vessels -> detections.csv")

    import matplotlib.pyplot as plt
    db = 10 * np.log10(np.clip(img, 1e-6, None))
    plt.figure(figsize=(10, 10))
    plt.imshow(db, cmap="gray", vmin=-35, vmax=0)
    for lon, lat, *_ in rows:
        xx, yy = tr.transform(lon, lat)
        plt.plot(np.searchsorted(x[sl[1]], xx), np.argmin(abs(y[sl[0]] - yy)), "r+", ms=8)
    plt.title(f"{pol} gamma0 [dB] + CFAR detections"); plt.savefig("detections.png", dpi=150)
    print("saved detections.png")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["search"]
    {"search": search, "inspect": inspect, "ships": ships}[cmd](*args)
