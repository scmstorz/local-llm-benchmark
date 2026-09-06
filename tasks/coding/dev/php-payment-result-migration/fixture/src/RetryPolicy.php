<?php

declare(strict_types=1);

namespace Benchmark\Payment;

use InvalidArgumentException;

final readonly class RetryPolicy
{
    public function __construct(private int $maxAttempts = 3)
    {
        if ($maxAttempts < 1) {
            throw new InvalidArgumentException('maxAttempts must be at least one');
        }
    }

    public function shouldRetry(PaymentResult $result, int $attemptNumber): bool
    {
        if ($attemptNumber < 1) {
            throw new InvalidArgumentException('attemptNumber must be at least one');
        }

        return $result->status !== PaymentStatus::Succeeded
            && $attemptNumber < $this->maxAttempts;
    }
}
