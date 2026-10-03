"""Availability-time guards and proper scores. Does not train or place trades."""
import math


def gate_inputs(decision_ns,inputs):
    if type(decision_ns) is not int:raise ValueError('Integer nanosecond clock required')
    for row in inputs:
        for key in ('event_ns','available_ns'):
            if type(row[key]) is not int:raise ValueError('Integer input clocks required')
        if row['available_ns']<row['event_ns']:raise ValueError('Input available before its event')
        if max(row['event_ns'],row['available_ns'])>decision_ns:raise ValueError('Future or not-yet-available input')
    return True


def gate_training(decision_ns,labels):
    for row in labels:
        if any(type(row[k]) is not int for k in ('target_end_ns','label_available_ns')):raise ValueError('Integer label clocks required')
        if row['label_available_ns']<row['target_end_ns']:raise ValueError('Label available before target ends')
        if row['label_available_ns']>decision_ns:raise ValueError('Unresolved training target')
    return True


def score(probabilities,returns,intervals,alpha=.2):
    if not 0<alpha<1:raise ValueError('Invalid miscoverage')
    if not probabilities or len(probabilities)!=len(returns) or len(intervals)!=len(returns):raise ValueError('Empty or mismatched forecasts')
    brier=[];winkler=[];covered=[]
    for p,r,(lower,upper) in zip(probabilities,returns,intervals):
        if not all(math.isfinite(x) for x in (p,r,lower,upper)) or not 0<=p<=1 or lower>upper:raise ValueError('Invalid forecast')
        brier.append((p-int(r>0))**2)
        winkler.append(upper-lower+2/alpha*max(lower-r,0)+2/alpha*max(r-upper,0))
        covered.append(lower<=r<=upper)
    n=len(returns)
    return dict(observations=n,brier=sum(brier)/n,winkler=sum(winkler)/n,interval_coverage=sum(covered)/n,nominal_coverage=1-alpha,
                target='positive return; zero return is class 0',return_units='same units as supplied intervals')


def skill(model_loss,baseline_loss):
    if not all(math.isfinite(x) and x>=0 for x in (model_loss,baseline_loss)):raise ValueError('Invalid losses')
    return 1-model_loss/baseline_loss if baseline_loss>0 else None
