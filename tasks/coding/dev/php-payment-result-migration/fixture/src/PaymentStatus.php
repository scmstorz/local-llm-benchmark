<?php

declare(strict_types=1);

namespace Benchmark\Payment;

enum PaymentStatus: string
{
    case Succeeded = 'succeeded';
    case Declined = 'declined';
    case RetryableFailure = 'retryable_failure';
    case Unknown = 'unknown';
}
