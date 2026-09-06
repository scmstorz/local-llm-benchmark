# Frozen reference dossier: reliable payment processing under retries

Retrieved: 2026-08-29

[S01] In a distributed system, a timeout is ambiguous. A client may fail to
receive a response even though the server completed the operation, or the
request may never have arrived. Retrying improves availability for transient
failures but can repeat a non-idempotent side effect. “Exactly once” is not a
property that a network can simply infer from an absent response.

Source: Amazon Builders' Library, “Making retries safe with idempotent APIs”  
https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/

[S02] A payment API can accept an idempotency key representing one logical
payment intent. Repeating the same request with that key should return or
reconstruct the same logical result instead of creating another charge. The
key needs a defined scope, persistence and expiry policy, and the service must
reject accidental reuse with materially different parameters. A random key per
retry defeats deduplication; one global key for different purchases conflates
distinct intents.

Sources: Amazon Builders' Library in [S01] and Stripe, “Idempotent requests”  
https://docs.stripe.com/api/idempotent_requests

[S03] Message brokers commonly provide at-least-once processing modes in which
a message can be delivered again after a crash or uncertain acknowledgement.
A consumer that charges first and records completion later can therefore
charge twice after failing between those actions. A durable inbox or processed
message record, unique business constraint, and idempotent state transition can
make duplicate delivery harmless—but checking and recording must be coordinated
with the local side effect.

Source: Apache Kafka, “Design”  
https://kafka.apache.org/design/

[S04] Kafka transactions and idempotent producers can give exactly-once
semantics for supported read-process-write flows whose outputs and offsets stay
inside Kafka. They do not automatically include an external payment provider,
email service or arbitrary database transaction. End-to-end guarantees depend
on every participating boundary and its failure protocol.

Source: Apache Kafka design documentation in [S03].

[S05] The transactional outbox pattern addresses a different dual-write
problem: business state and an outgoing event are written atomically to the
same local database transaction. A relay later publishes the outbox record.
The relay may publish more than once, so event identifiers and idempotent
consumers are still required. An outbox does not by itself make an external
charge atomic with the local database.

Source: Debezium, “Outbox Event Router”  
https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html

[S06] Payment handling should be modeled as a state machine with stable
business identifiers and explicit states such as initiated, pending,
succeeded, failed, cancelled or refund-pending. Concurrency control and unique
constraints prevent two workers from advancing one intent incompatibly.
Provider status queries, webhooks and reconciliation jobs repair ambiguous or
missed transitions; high-risk exceptions may require an auditable manual path.

This operational synthesis is project-authored from [S01] through [S05].

[S07] A defensible design states its guarantee and boundary: duplicate messages
may occur, but one logical payment intent should have at most one successful
charge at the provider, and local state should eventually converge to the
provider's authoritative result. Achieving this typically combines stable
idempotency at the external API, durable local deduplication and state,
transactional publication of subsequent events, retry policies, observability
and reconciliation. No single “exactly once” switch replaces these layers.

This synthesis is project-authored from [S01] through [S06].
