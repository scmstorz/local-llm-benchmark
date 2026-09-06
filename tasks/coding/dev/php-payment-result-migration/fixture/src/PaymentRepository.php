<?php

declare(strict_types=1);

namespace Benchmark\Payment;

interface PaymentRepository
{
    public function stateFor(string $orderId): PaymentState;

    public function markPaid(string $orderId, string $providerReference): void;

    public function markDeclined(string $orderId, string $reason): void;

    public function markPending(string $orderId, string $reason): void;
}
