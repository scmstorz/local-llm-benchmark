<?php

declare(strict_types=1);

namespace Benchmark\Payment;

use InvalidArgumentException;

final readonly class PaymentResult
{
    private function __construct(
        public PaymentStatus $status,
        public ?string $providerReference,
        public ?string $reason,
    ) {
    }

    public static function succeeded(string $providerReference): self
    {
        if ($providerReference === '') {
            throw new InvalidArgumentException('provider reference must not be empty');
        }

        return new self(PaymentStatus::Succeeded, $providerReference, null);
    }

    public static function declined(string $reason): self
    {
        return new self(PaymentStatus::Declined, null, self::requiredReason($reason));
    }

    public static function retryableFailure(string $reason): self
    {
        return new self(
            PaymentStatus::RetryableFailure,
            null,
            self::requiredReason($reason),
        );
    }

    public static function unknown(string $reason): self
    {
        return new self(PaymentStatus::Unknown, null, self::requiredReason($reason));
    }

    private static function requiredReason(string $reason): string
    {
        if ($reason === '') {
            throw new InvalidArgumentException('payment reason must not be empty');
        }

        return $reason;
    }
}
