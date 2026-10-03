"""Factorized six-field event IDs and training-only reconstructable quantiles."""
import numpy as np

class QuantileCodec:
    def __init__(self,bins=32):
        if bins not in (16,32,64):raise ValueError('Use registered 16/32/64-bin comparisons')
        self.bins=bins
    def fit(self,values,available_ns,cutoff_ns,window_ns=None):
        x=np.asarray(values,float);t=np.asarray(available_ns,dtype=np.int64)
        if x.ndim!=1 or x.shape!=t.shape or not len(x) or not np.isfinite(x).all():raise ValueError('Invalid training series')
        if np.any(t>cutoff_ns):raise ValueError('Future data supplied to fit')
        keep=np.ones(len(x),bool) if window_ns is None else t>cutoff_ns-window_ns
        x=x[keep]
        if not len(x):raise ValueError('Empty rolling history')
        self.cutoff_ns=int(cutoff_ns);self.cuts=np.quantile(x,np.arange(1,self.bins)/self.bins);self.lower=float(x.min());self.upper=float(x.max());b=np.searchsorted(self.cuts,x,side='right');self.centers=np.array([np.median(x[b==i]) if np.any(b==i) else np.quantile(x,(i+.5)/self.bins) for i in range(self.bins)])
        return self
    def encode(self,values):
        x=np.asarray(values,float);b=1+np.searchsorted(self.cuts,x,side='right');b=np.where(x<self.lower,0,b);b=np.where(x>self.upper,self.bins+1,b);return np.where(np.isfinite(x),b,self.bins+2).astype(int)
    def decode(self,tokens):
        b=np.asarray(tokens,int)
        if np.any((b<0)|(b>self.bins+2)):raise ValueError('Invalid token')
        lookup=np.r_[self.lower,self.centers,self.upper,np.nan];return lookup[b]
    def audit(self,train,later):
        a=self.encode(train);b=self.encode(later);decoded=self.decode(b);p=np.bincount(a,minlength=self.bins+3)/len(a);q=np.bincount(b,minlength=self.bins+3)/len(b);mid=(p+q)/2
        def kl(x):
            mask=x>0;return float(np.sum(x[mask]*np.log(x[mask]/mid[mask])))
        finite=np.isfinite(later)&np.isfinite(decoded)
        return dict(mae=float(np.mean(np.abs(np.asarray(later)[finite]-decoded[finite]))),rmse=float(np.sqrt(np.mean((np.asarray(later)[finite]-decoded[finite])**2))),frequency_js_divergence=(kl(p)+kl(q))/2,range_exceedance_fraction=float(np.mean((b==0)|(b==self.bins+1))),train_frequencies=p.tolist(),later_frequencies=q.tolist())

class SixFieldTokenizer:
    """Each token has its own embedding ID range; no Cartesian-product dictionary."""
    types=('trade','limit','add','cancel','book_change','unknown')
    sides=('buy','sell','unknown')
    # 16 magnitude categories x 2 signs = 32 level IDs. Exact ticks near touch.
    level_edges=np.array([.5,1.5,2.5,3.5,4.5,5.5,7.5,10.5,14.5,20.5,32.5,64.5,128.5,256.5,512.5])
    def __init__(self,size_codec,gap_codec,clusters=16):
        if clusters<1:raise ValueError('Positive cluster budget required')
        self.size=size_codec;self.gap=gap_codec;self.clusters=clusters
        widths=[len(self.types),len(self.sides),33,size_codec.bins+3,gap_codec.bins+3,clusters+1];self.offsets=np.r_[0,np.cumsum(widths)[:-1]];self.vocabulary_size=sum(widths)
    def encode(self,kind,side,distance_ticks,quantity,dt_seconds,participant=None,decision_ns=None,cluster_fit_ns=None):
        if decision_ns is None or max(self.size.cutoff_ns,self.gap.cutoff_ns)>decision_ns:raise ValueError('Codec unavailable at decision')
        if participant is not None and (not 0<=participant<self.clusters or cluster_fit_ns is None or cluster_fit_ns>decision_ns):raise ValueError('Participant provenance invalid')
        if quantity is not None and (not np.isfinite(quantity) or quantity<0):raise ValueError('Invalid size')
        if dt_seconds is not None and (not np.isfinite(dt_seconds) or dt_seconds<0):raise ValueError('Invalid gap')
        level=32 if distance_ticks is None else int(np.searchsorted(self.level_edges,abs(distance_ticks)))+16*int(distance_ticks<0)
        if distance_ticks is not None and not np.isfinite(distance_ticks):raise ValueError('Invalid level')
        bucket=[self.types.index(kind),self.sides.index(side),level,int(self.size.encode([np.nan if quantity is None else np.log1p(quantity)])[0]),int(self.gap.encode([np.nan if dt_seconds is None else np.log1p(dt_seconds)])[0]),self.clusters if participant is None else participant]
        return (self.offsets+bucket).tolist()


class SummaryTokenizer:
    fields=('volatility','spread','book_imbalance','funding','open_interest_change','regime')
    def __init__(self,codecs):
        if set(codecs)!=set(self.fields):raise ValueError('All summary codec fields required')
        self.codecs=codecs;self.offsets=np.r_[0,np.cumsum([codecs[f].bins+3 for f in self.fields])[:-1]]
        self.vocabulary_size=sum(codecs[f].bins+3 for f in self.fields)
    def encode(self,values,period_end_ns,available_ns,decision_ns):
        if period_end_ns>available_ns or available_ns>decision_ns:raise ValueError('Future or unfinished summary')
        if any(c.cutoff_ns>decision_ns for c in self.codecs.values()):raise ValueError('Future fitted summary codec')
        if set(values)-set(self.fields):raise ValueError('Unknown summary field')
        return [int(offset+c.encode([values.get(field,np.nan)])[0]) for field,offset,c in zip(self.fields,self.offsets,(self.codecs[f] for f in self.fields))]
