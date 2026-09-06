# Frozen reference dossier: leakage and selection bias in ML evaluation

Retrieved: 2026-08-29

[S01] Data leakage occurs when information unavailable at real prediction time
influences model fitting or evaluation. Preprocessing is part of fitting: an
imputer, scaler or feature selector learns parameters from data. Fitting these
steps on the full dataset before cross-validation lets validation folds
influence the representation used to train their models, producing optimistic
estimates even if labels are not explicitly copied.

Source: scikit-learn, “Common pitfalls and recommended practices”  
https://scikit-learn.org/stable/common_pitfalls.html

[S02] A pipeline keeps preprocessing and prediction together. In each
cross-validation split, learned preprocessing must be fit only on that split's
training portion and then applied unchanged to its validation portion. Steps
that use the target, such as supervised feature selection, are especially
obvious leakage risks, but unsupervised transformations can leak distribution
information too.

Source: scikit-learn common-pitfalls guidance in [S01].

[S03] If many model families, hyperparameters or feature sets are tried and the
highest cross-validation score is reported, the evaluation criterion itself
has been optimized. Random variation favors some candidate, so the selected
maximum is an optimistic estimate. Model selection is part of the training
procedure, not an independent test of that procedure.

Source: Cawley and Talbot, “On Over-fitting in Model Selection and Subsequent
Selection Bias in Performance Evaluation,” JMLR 11 (2010)  
https://www.jmlr.org/beta/papers/v11/cawley10a.html

[S04] Nested cross-validation separates these roles. For every outer split,
all tuning and preprocessing occur within the outer training data, commonly by
inner cross-validation. The selected pipeline is evaluated once on that outer
test fold. Aggregated outer-fold results estimate the performance of the whole
selection procedure. Nested CV does not identify one universal final model; a
final configuration is then chosen using all development data under a frozen
procedure.

Source: scikit-learn, “Nested versus non-nested cross-validation”  
https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html

[S05] A final untouched test set can provide one additional estimate after the
entire pipeline, search space, metric and decision rule are frozen. Repeatedly
checking it and changing the system turns it into development data and leaks
test feedback. A new external or temporally later test is then needed for a
clean confirmation.

Sources: scikit-learn and Cawley and Talbot sources in [S01] and [S03].

[S06] Splits must match the deployment unit. Multiple rows from one patient,
customer, device or site should not straddle train and test when the goal is
generalization to new groups. Time-dependent prediction generally requires
training on the past and testing on later data rather than random shuffling.
Class balance alone does not fix group, temporal or other dependency leakage.

Source: scikit-learn, “Cross-validation: evaluating estimator performance”  
https://scikit-learn.org/stable/modules/cross_validation.html

[S07] Performance should be reported with the metric appropriate to the task,
the split and selection protocol, uncertainty or fold variation, and all
material preprocessing and tuning choices. Nested CV reduces a specific
selection bias but does not cure dataset shift, a nonrepresentative sample,
label leakage already present in features, a poor metric or a tiny dataset.
The target claim must state the population, time and unit to which results are
supposed to generalize.

This synthesis is project-authored from [S01] through [S06].
