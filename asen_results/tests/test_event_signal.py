import numpy as np
import pandas as pd
from terraguard.event_signal import contrast, masks, window, effects, event_effects, matched_passes, split_for


def test_linear_mean_and_missing_coverage():
    disks, ring = masks()
    a=np.ones((64,64)); a[disks[30]]=2
    valid=np.ones_like(a,dtype=bool)
    assert np.isclose(contrast(a,valid,disks[30],ring),10*np.log10(2))
    valid[disks[30]]=False
    assert np.isnan(contrast(a,valid,disks[30],ring))


def test_strict_windows():
    assert [window(x) for x in [-31,-30,-.01,0,29.9,30,90,90.1]] == ['other','pre','pre','other','other','post','post','other']


def test_event_weighting_and_pass_requirements():
    rows=[]
    for event,stack,pre,post in [(1,'a',4,1),(1,'b',2,1),(2,'a',1,1)]:
        for w,v in [('pre',pre),('post',post)]:
            for _ in range(2): rows.append(dict(incident_id=event,stack=stack,polarization='hh',radius_m=30,window=w,matched=v,split='validation',gpm=20))
    s=effects(pd.DataFrame(rows),2)
    e=event_effects(s).set_index('incident_id')
    assert e.loc[1,'effect_db']==2
    assert e.loc[2,'effect_db']==0
    assert effects(pd.DataFrame(rows),3).empty


def test_fixed_control_placebo_does_not_cancel():
    rows=[]
    for sid,typ,val in [('leak_1','incident',5),('ctl_1_c0','control',3),('ctl_1_c1','control',1),('ctl_1_c2','control',2)]:
        row=dict(incident_id=1,stack='a',pass_id='p',site_id=sid,site_type=typ,delta_days=-5,gpm=20,split=split_for(1))
        row.update({f'{p}_{r}':val for p in ['hh','hv'] for r in [10,30,60]});rows.append(row)
    result=matched_passes(pd.DataFrame(rows))
    assert np.allclose(result.matched,3)
    assert np.allclose(result.placebo,1.5)
