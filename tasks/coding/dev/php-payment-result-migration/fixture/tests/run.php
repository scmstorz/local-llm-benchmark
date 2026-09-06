<?php

declare(strict_types=1);

require_once __DIR__ . '/bootstrap.php';

use Benchmark\Payment\CheckoutOutcome;
use Benchmark\Payment\CheckoutService;
use Benchmark\Payment\Order;
use Benchmark\Payment\PaymentResult;
use Benchmark\Payment\RetryPolicy;
use Benchmark\Payment\Tests\FakePaymentGateway;
use Benchmark\Payment\Tests\InMemoryPaymentRepository;
use function Benchmark\Payment\Tests\assertSameValue;
use function Benchmark\Payment\Tests\requestKeys;

$cases = [];

$cases['successful charge is recorded once'] = static function (): void {
    $gateway = new FakePaymentGateway([PaymentResult::succeeded('provider-1')]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    $outcome = $service->checkout(new Order('order-1', 1299));

    assertSameValue(CheckoutOutcome::Paid, $outcome);
    assertSameValue(['checkout:order-1'], requestKeys($gateway->requests));
    assertSameValue(
        [['type' => 'paid', 'order_id' => 'order-1', 'detail' => 'provider-1']],
        $repository->writes,
    );
};

$cases['decline is final and is not retried'] = static function (): void {
    $gateway = new FakePaymentGateway([PaymentResult::declined('insufficient_funds')]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    $outcome = $service->checkout(new Order('order-2', 2500));

    assertSameValue(CheckoutOutcome::Declined, $outcome);
    assertSameValue(['checkout:order-2'], requestKeys($gateway->requests));
    assertSameValue(
        [[
            'type' => 'declined',
            'order_id' => 'order-2',
            'detail' => 'insufficient_funds',
        ]],
        $repository->writes,
    );
};

$cases['retryable failure can recover with the same key'] = static function (): void {
    $gateway = new FakePaymentGateway([
        PaymentResult::retryableFailure('gateway_busy'),
        PaymentResult::succeeded('provider-3'),
    ]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    $outcome = $service->checkout(new Order('order-3', 999));

    assertSameValue(CheckoutOutcome::Paid, $outcome);
    assertSameValue(
        ['checkout:order-3', 'checkout:order-3'],
        requestKeys($gateway->requests),
    );
    assertSameValue('paid', $repository->writes[0]['type']);
};

$cases['unknown result becomes pending without a retry'] = static function (): void {
    $gateway = new FakePaymentGateway([PaymentResult::unknown('timeout')]);
    $repository = new InMemoryPaymentRepository();
    $service = new CheckoutService($gateway, $repository, new RetryPolicy(3));

    $outcome = $service->checkout(new Order('order-4', 5000));

    assertSameValue(CheckoutOutcome::Pending, $outcome);
    assertSameValue(['checkout:order-4'], requestKeys($gateway->requests));
    assertSameValue(
        [['type' => 'pending', 'order_id' => 'order-4', 'detail' => 'timeout']],
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

echo count($cases) - $failures, '/', count($cases), ' public checks passed', PHP_EOL;
if ($failures > 0) {
    exit(1);
}
