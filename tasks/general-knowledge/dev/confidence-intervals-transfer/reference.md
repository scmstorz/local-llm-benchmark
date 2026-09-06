# Frozen reference dossier: comparing two apparently conflicting studies

Retrieved: 2026-08-28

[S01] Frozen scenario. A company is considering a digital learning program. The
outcome is an objective test-score change measured on the same scale in both
studies. Before seeing either study, the company defined an improvement of at
least 0.50 points as practically relevant.

Study A is observational. Among 10,000 voluntary platform users, participants
chose whether to use the program. Researchers adjusted for age and baseline
score, but motivation was not measured. The adjusted association is +0.20
points with a 95% confidence interval of [0.14, 0.26].

Study B randomized 200 eligible users, 100 to the program and 100 to control.
Its estimated average treatment effect is +0.80 points with a 95% confidence
interval of [-0.10, 1.70]. Assume both intervals were computed with appropriate
methods for their stated estimands and that no outcome switching or selective
reporting occurred.

The numerical scenario and practical threshold are project-authored.

[S02] Confidence-interval width reflects sampling precision under the interval
procedure. A larger sample generally reduces the standard error and narrows the
interval, while greater variability widens it. Nominal coverage remains
conditional on the sampling design, model and assumptions. A narrow interval
does not include a correction for an unmeasured systematic bias merely because
the sample is large.

Sources: NIST/SEMATECH e-Handbook, “Confidence Limits for the Mean” and
“Confidence Intervals”  
https://itl.nist.gov/div898/handbook/eda/section3/eda352.htm  
https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm

[S03] For a conventional two-sided test and its corresponding 95% confidence
interval, excluding the null value zero corresponds to rejection at the 5%
level, while including zero corresponds to not rejecting that null value. This
is conditional on using matching test and interval procedures. Failure to
reject zero is not proof that the effect equals zero; the interval shows which
effect sizes remain compatible with the data and method.

Sources: NIST/SEMATECH e-Handbook, “What is the relationship between a test and
a confidence interval?” and “Confidence interval approach”  
https://www.itl.nist.gov/div898/handbook/prc/section1/prc15.htm  
https://itl.nist.gov/div898/handbook/prc/section2/prc221.htm

[S04] Statistical significance does not measure effect size or practical
importance. Scientific, business and policy conclusions should not be based
only on whether a p-value crosses a threshold. The estimated magnitude,
uncertainty, study design, data quality, consequences and a substantively
defined relevance threshold all matter.

Source: American Statistical Association, “Statement on Statistical
Significance and P-Values”  
https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf

[S05] One estimate being statistically significant and another not being
statistically significant does not itself establish a statistically significant
difference between the two effects. Comparing the studies requires a direct
contrast or joint model, together with attention to whether their populations,
estimands and designs are sufficiently comparable.

Source: Andrew Gelman and Hal Stern, “The Difference Between ‘Significant’ and
‘Not Significant’ is not Itself Statistically Significant”  
https://sites.stat.columbia.edu/gelman/research/unpublished/signif3.pdf

[S06] Random assignment makes treatment and control groups comparable on
average and minimizes confounding, so a well-executed randomized experiment
usually provides a more secure basis for causal inference than an observational
comparison. Randomization does not guarantee perfect balance in a small sample,
eliminate every conduct or measurement problem, or automatically establish
generalizability beyond the studied participants.

Source: National Academies, “Reference Guide on Statistics and Research
Methods,” hosted by NCBI Bookshelf  
https://www.ncbi.nlm.nih.gov/books/NBK621595/?report=printable

[S07] Applied to the frozen scenario, Study A is much more precise about its
adjusted observational association and excludes both zero and the predeclared
+0.50 relevance threshold. Conditional on its model, it is statistically
different from zero but points to an association smaller than the company's
practical threshold. Unmeasured motivation can still bias the association, so
the narrow interval does not establish a small causal effect.

Study B has the stronger design for estimating a causal effect but is
imprecise. Its interval includes zero and therefore is not statistically
significant at the matching two-sided 5% level. It also includes effects below
and above +0.50, so it neither establishes a practically relevant benefit nor
rules one out. The +0.80 point estimate is practically relevant by the stated
threshold, but the uncertainty is too large for a confident conclusion.

This application is project-authored from [S01] through [S06].

[S08] A defensible decision summary is therefore not “A proves a small effect
and B proves no effect.” The studies answer different evidential questions and
are not demonstrated to contradict each other. A larger, well-conducted
randomized study designed to estimate effects around the +0.50 threshold would
reduce the decision-relevant uncertainty. Merely adding more self-selected
observational users would improve precision without resolving unmeasured
confounding. Costs, risks and reversibility of the business decision can affect
what action is reasonable under the remaining uncertainty, but they do not
change what the studies establish.

This decision synthesis is project-authored from [S01] through [S07].

