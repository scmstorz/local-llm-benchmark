<?php

declare(strict_types=1);

if ($argc !== 2) {
    throw new RuntimeException('usage: hidden_tests.php FIXTURE_ROOT');
}

$fixtureRoot = realpath($argv[1]);
if ($fixtureRoot === false) {
    throw new RuntimeException('fixture root does not exist');
}

require_once $fixtureRoot . '/tests/bootstrap.php';

use Benchmark\Payment\CheckoutOutcome;
use Benchmark\Payment\CheckoutService;
use Benchmark\Payment\Order;
use Benchmark\Payment\PaymentResult;
use Benchmark\Payment\PaymentState;
use Benchmark\Payment\RetryPolicy;
use Benchmark\Payment\Tests\FakePaymentGateway;
use Benchmark\Payment\Tests\InMemoryPaymentRepository;
use function Benchmark\Payment\Tests\assertSameValue;
use function Benchmark\Payment\Tests\assertThrows;
use function Benchmark\Payment\Tests\requestKeys;

$cases = [];

$cases['preserves retry-policy validation'] = static function (): void {
    assertThrows(InvalidArgumentException::class, static fn () => new RetryPolicy(0));
    $policy = new RetryPolicy(2);
    assertThrows(
        InvalidArgumentException::class,
        static fn () => $policy->shouldRetry(
            PaymentResult::retryableFailure('temporary'),
            0,
        ),
    );
};

$cases['retries only retryable failures before the cap'] = static function (): void {
    $policy = new RetryPolicy(3);

    assertSameValue(
        true,
        $policy->shouldRetry(PaymentResult::retryableFailure('temporary'), 1),
    );
    assertSameValue(
        false,
        $policy->shouldRetry(PaymentResult::retryableFailure('temporary'), 3),
    );
    assertSameValue(false, $policy->shouldRetry(PaymentResult::declined('no'), 1));
    assertSameValue(false, $policy->shouldRetry(PaymentResult::unknown('timeout'), 1));
    assertSameValue(
        false,
        $policy->shouldRetry(PaymentResult::succeeded('provider'), 1),
    );
};

$cases['already-paid order bypasses the gateway and writes'] = static function (): void {
    $gateway = new FakePaymentGateway([]);
    $repository = new InMemoryPaymentRepository(['paid-order' => PaymentState::Paid]);
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    assertSameValue(
        CheckoutOutcome::Paid,
        $service->checkout(new Order('paid-order', 1500)),
    );
    assertSameValue([], $gateway->requests);
    assertSameValue([], $repository->writes);
};

$cases['final declined and pending states bypass the gateway'] = static function (): void {
    $gateway = new FakePaymentGateway([]);
    $repository = new InMemoryPaymentRepository([
        'declined-order' => PaymentState::Declined,
        'pending-order' => PaymentState::Pending,
    ]);
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    assertSameValue(
        CheckoutOutcome::Declined,
        $service->checkout(new Order('declined-order', 1500)),
    );
    assertSameValue(
        CheckoutOutcome::Pending,
        $service->checkout(new Order('pending-order', 1500)),
    );
    assertSameValue([], $gateway->requests);
    assertSameValue([], $repository->writes);
};

$cases['exhausted retryable failures become pending'] = static function (): void {
    $gateway = new FakePaymentGateway([
        PaymentResult::retryableFailure('busy-1'),
        PaymentResult::retryableFailure('busy-2'),
        PaymentResult::retryableFailure('busy-3'),
    ]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    assertSameValue(
        CheckoutOutcome::Pending,
        $service->checkout(new Order('retry-order', 1500)),
    );
    assertSameValue(
        ['checkout:retry-order', 'checkout:retry-order', 'checkout:retry-order'],
        requestKeys($gateway->requests),
    );
    assertSameValue(
        [['type' => 'pending', 'order_id' => 'retry-order', 'detail' => 'busy-3']],
        $repository->writes,
    );
};

$cases['reuses one stable key across every retry'] = static function (): void {
    $gateway = new FakePaymentGateway([
        PaymentResult::retryableFailure('busy-1'),
        PaymentResult::retryableFailure('busy-2'),
        PaymentResult::succeeded('provider-retry'),
    ]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(4));

    assertSameValue(
        CheckoutOutcome::Paid,
        $service->checkout(new Order('stable-order', 1500)),
    );
    assertSameValue(
        ['checkout:stable-order', 'checkout:stable-order', 'checkout:stable-order'],
        requestKeys($gateway->requests),
    );
};

$cases['decline after a retryable failure stops immediately'] = static function (): void {
    $gateway = new FakePaymentGateway([
        PaymentResult::retryableFailure('busy'),
        PaymentResult::declined('insufficient_funds'),
    ]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(4));

    assertSameValue(
        CheckoutOutcome::Declined,
        $service->checkout(new Order('mixed-order', 1500)),
    );
    assertSameValue(2, count($gateway->requests));
    assertSameValue(
        [[
            'type' => 'declined',
            'order_id' => 'mixed-order',
            'detail' => 'insufficient_funds',
        ]],
        $repository->writes,
    );
};

$cases['successful retry records exactly one paid transition'] = static function (): void {
    $gateway = new FakePaymentGateway([
        PaymentResult::retryableFailure('busy'),
        PaymentResult::succeeded('provider-final'),
    ]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    assertSameValue(
        CheckoutOutcome::Paid,
        $service->checkout(new Order('success-order', 1500)),
    );
    assertSameValue(
        [[
            'type' => 'paid',
            'order_id' => 'success-order',
            'detail' => 'provider-final',
        ]],
        $repository->writes,
    );
};

$failures = 0;
foreach ($cases as $name => $run) {
    try {
        $run();
        echo 'ok - ', $name, PHP_EOL;
    } catch (Throwable $error) {
        $failures++;
        fwrite(STDERR, 'not ok - ' . $name . PHP_EOL . $error . PHP_EOL);
    }
}

echo count($cases) - $failures, '/', count($cases), ' hidden checks passed', PHP_EOL;
if ($failures > 0) {
    exit(1);
}
