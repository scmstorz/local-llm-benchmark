<?php

declare(strict_types=1);

namespace Benchmark\Payment;

enum CheckoutOutcome: string
{
    case Paid = 'paid';
    case Declined = 'declined';
    case Pending = 'pending';
}
