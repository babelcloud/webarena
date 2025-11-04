import GboxSDK from 'gbox-sdk';

async function testTraceScreenshot() {
  const apiKey = process.env.GBOX_API_KEY;

  if (!apiKey) {
    console.error('GBOX_API_KEY environment variable not set');
    process.exit(1);
  }

  const gboxSDK = new GboxSDK({ apiKey });
  const boxId = '60165e37-5c18-41fb-aa49-ebe3a69b5f5c';

  const box = await gboxSDK.get(boxId);

  const result = await box.action.click({
    target: 'Chromium icon',
    options: {
      screenshot: {
        phases: ['after', 'trace'],
        outputFormat: 'base64',
        delay: '500ms',
      },
    },
  });

  console.log('\n=== RESULT ===');
  console.log('Action ID:', result.actionId);
  console.log('Message:', result.message);

  console.log('\n=== SCREENSHOT STRUCTURE ===');
  console.log('Screenshot object:', result.screenshot);

  console.log('\n=== TRACE SCREENSHOT ===');
  if (result.screenshot?.trace) {
    console.log('Trace exists:', true);
    console.log('Trace URI exists:', !!result.screenshot.trace.uri);
    console.log('Trace URI length:', result.screenshot.trace.uri?.length || 0);
    console.log('Trace URI preview:', result.screenshot.trace.uri?.substring(0, 100) + '...');
  } else {
    console.log('Trace exists:', false);
  }

  console.log('\n=== AFTER SCREENSHOT ===');
  if (result.screenshot?.after) {
    console.log('After exists:', true);
    console.log('After URI exists:', !!result.screenshot.after.uri);
    console.log('After URI length:', result.screenshot.after.uri?.length || 0);
    console.log('After URI preview:', result.screenshot.after.uri?.substring(0, 100) + '...');
  } else {
    console.log('After exists:', false);
  }

  console.log('\n=== FULL RESULT (stringified) ===');
  console.log(JSON.stringify({
    actionId: result.actionId,
    message: result.message,
    screenshot: {
      trace: result.screenshot?.trace ? { uriLength: result.screenshot.trace.uri?.length, hasUri: !!result.screenshot.trace.uri } : undefined,
      after: result.screenshot?.after ? { uriLength: result.screenshot.after.uri?.length, hasUri: !!result.screenshot.after.uri } : undefined,
    }
  }, null, 2));
}

testTraceScreenshot().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
