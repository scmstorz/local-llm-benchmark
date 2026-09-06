<?php

declare(strict_types=1);

namespace Benchmark\Payment;

final readonly class CheckoutService
{
    public function __construct(
        private PaymentGateway $gateway,
        private PaymentRepository $repository,
        private RetryPolicy $retryPolicy,
    ) {
    }

    public function checkout(Order $order): CheckoutOutcome
    {
        $request = new PaymentRequest(
            $order->id,
            $order->amountCents,
            'checkout:' . $order->id,
        );
        $attemptNumber = 1;

        while (true) {
            $result = $this->gateway->charge($request);

            if ($result->status === PaymentStatus::Succeeded) {
                $this->repository->markPaid(
                    $order->id,
                    $result->providerReference,
                );

                return CheckoutOutcome::Paid;
            }

            if ($this->retryPolicy->shouldRetry($result, $attemptNumber)) {
                $attemptNumber++;
                continue;
            }

            $this->repository->markDeclined($order->id, $result->reason);

            return CheckoutOutcome::Declined;
        }
    }
}
