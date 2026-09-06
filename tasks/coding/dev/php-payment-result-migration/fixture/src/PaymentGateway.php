<?php

declare(strict_types=1);

namespace Benchmark\Payment;

interface PaymentGateway
{
    public function charge(PaymentRequest $request): PaymentResult;
}
