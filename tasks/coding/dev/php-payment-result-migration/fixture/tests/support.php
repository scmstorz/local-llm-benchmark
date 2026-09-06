<?php

declare(strict_types=1);

namespace Benchmark\Payment\Tests;

use Benchmark\Payment\PaymentGateway;
use Benchmark\Payment\PaymentRepository;
use Benchmark\Payment\PaymentRequest;
use Benchmark\Payment\PaymentResult;
use Benchmark\Payment\PaymentState;
use LogicException;
use RuntimeException;
use Throwable;

final class FakePaymentGateway implements PaymentGateway
{
    /** @var list<PaymentRequest> */
    public array $requests = [];

    /** @param list<PaymentResult> $results */
    public function __construct(private array $results)
    {
    }

    public function charge(PaymentRequest $request): PaymentResult
    {
        $this->requests[] = $request;
        if ($this->results === []) {
            throw new LogicException('unexpected extra gateway call');
        }

        return array_shift($this->results);
    }
}

final class InMemoryPaymentRepository implements PaymentRepository
{
    /** @var list<array{type: string, order_id: string, detail: string}> */
    public array $writes = [];

    /** @param array<string, PaymentState> $states */
    public function __construct(private array $states = [])
    {
    }

    public function stateFor(string $orderId): PaymentState
    {
        return $this->states[$orderId] ?? PaymentState::Unpaid;
    }

    public function markPaid(string $orderId, string $providerReference): void
    {
        $this->states[$orderId] = PaymentState::Paid;
        $this->writes[] = [
            'type' => 'paid',
            'order_id' => $orderId,
            'detail' => $providerReference,
        ];
    }

    public function markDeclined(string $orderId, string $reason): void
    {
        $this->states[$orderId] = PaymentState::Declined;
        $this->writes[] = [
            'type' => 'declined',
            'order_id' => $orderId,
            'detail' => $reason,
        ];
    }

    public function markPending(string $orderId, string $reason): void
    {
        $this->states[$orderId] = PaymentState::Pending;
        $this->writes[] = [
            'type' => 'pending',
            'order_id' => $orderId,
            'detail' => $reason,
        ];
    }
}

function assertSameValue(mixed $expected, mixed $actual, string $message = ''): void
{
    if ($expected !== $actual) {
        $prefix = $message === '' ? '' : $message . ': ';
        throw new RuntimeException(
            $prefix . 'expected ' . var_export($expected, true)
            . ', got ' . var_export($actual, true),
        );
    }
}

function assertThrows(string $exceptionClass, callable $callback): void
{
    try {
        $callback();
    } catch (Throwable $error) {
        if ($error instanceof $exceptionClass) {
            return;
        }
        throw new RuntimeException(
            'expected ' . $exceptionClass . ', got ' . $error::class,
            previous: $error,
        );
    }

    throw new RuntimeException('expected ' . $exceptionClass . ' to be thrown');
}

/** @param list<PaymentRequest> $requests */
function requestKeys(array $requests): array
{
    return array_map(
        static fn (PaymentRequest $request): string => $request->idempotencyKey,
        $requests,
    );
}
