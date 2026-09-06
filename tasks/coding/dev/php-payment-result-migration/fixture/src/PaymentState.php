<?php

declare(strict_types=1);

namespace Benchmark\Payment;

enum PaymentState: string
{
    case Unpaid = 'unpaid';
    case Paid = 'paid';
    case Declined = 'declined';
    case Pending = 'pending';
}
