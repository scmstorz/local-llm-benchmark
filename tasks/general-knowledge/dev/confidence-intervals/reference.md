# Frozen reference dossier: 95% confidence intervals

Retrieved: 2026-08-28

[S01] In the frequentist framework, a confidence interval is produced by a
repeatable statistical procedure. If the procedure for a nominal 95% interval
were applied across many independent samples under the same conditions,
approximately 95% of the resulting intervals would contain the fixed unknown
parameter. Once one particular interval has been calculated, it either
contains that parameter or it does not; the frequentist 95% does not assign a
95% probability to this already fixed parameter being inside this particular
realized interval.

Source: NIST/SEMATECH e-Handbook, “Confidence Limits for the Mean”  
https://itl.nist.gov/div898/handbook/eda/section3/eda352.htm

[S02] For a familiar mean interval, the estimate is surrounded by a margin of
error based on a standard error and a critical value. Other things equal, a
larger sample reduces the standard error and narrows the interval; greater
observed variability widens it; and demanding a higher confidence level
requires a wider interval. A narrow interval indicates greater sampling
precision under the method, not protection against biased sampling,
measurement error or an unsuitable model.

Sources: NIST/SEMATECH e-Handbook, “Confidence Limits for the Mean” and
“Confidence Intervals”  
https://itl.nist.gov/div898/handbook/eda/section3/eda352.htm  
https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm

[S03] The advertised coverage is conditional on the sampling design, model and
assumptions used by the interval procedure. For example, a textbook small-
sample interval for a mean commonly relies on independent observations and a
normal-population or justified approximation assumption. Increasing the
sample size can reduce random uncertainty, but it does not automatically
remove systematic bias or repair nonrepresentative data.

Source: NIST/SEMATECH e-Handbook, “Confidence Limits for the Mean”  
https://itl.nist.gov/div898/handbook/eda/section3/eda352.htm

[S04] A confidence interval for a mean concerns uncertainty about an unknown
population mean or fitted mean response. It is not a claim that 95% of the
individual observations lie inside the interval. A prediction interval answers
a different question: where a future individual observation may fall. It must
include both uncertainty in the estimated mean and individual-observation
variation, so it is normally wider than the corresponding confidence interval
for the mean response.

Source: NIST/SEMATECH e-Handbook, “Prediction intervals”  
https://www.itl.nist.gov/div898/handbook/pmd/section5/pmd512.htm

[S05] Example: suppose a valid method produces a 95% interval of 48 to 52 for a
population mean. A useful frequentist statement is that the method used has 95%
long-run coverage under its assumptions, and this run produced the interval
[48, 52]. It is not correct in strict frequentist language to say that this
fixed parameter now has a 95% probability of lying between 48 and 52, nor that
95% of future individual measurements will lie there.

This numerical example is project-authored and instantiates the distinctions
in [S01] and [S04].

