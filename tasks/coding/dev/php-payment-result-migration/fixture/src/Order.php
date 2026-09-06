<?php

declare(strict_types=1);

namespace Benchmark\Payment;

use InvalidArgumentException;

final readonly class Order
{
    public function __construct(
        public string $id,
        public int $amountCents,
    ) {
        if ($id === '') {
            throw new InvalidArgumentException('order id must not be empty');
        }
        if ($amountCents < 1) {
            throw new InvalidArgumentException('amountCents must be positive');
        }
    }
}
