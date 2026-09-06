<?php

declare(strict_types=1);

namespace Benchmark\Payment;

use InvalidArgumentException;

final readonly class PaymentRequest
{
    public function __construct(
        public string $orderId,
        public int $amountCents,
        public string $idempotencyKey,
    ) {
        if ($orderId === '' || $idempotencyKey === '') {
            throw new InvalidArgumentException('payment identifiers must not be empty');
        }
        if ($amountCents < 1) {
            throw new InvalidArgumentException('amountCents must be positive');
        }
    }
}
