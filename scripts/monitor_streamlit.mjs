import { mkdir } from "node:fs/promises";

import { chromium } from "playwright";

const appUrl = process.env.STREAMLIT_APP_URL;
const expectedText = process.env.STREAMLIT_EXPECTED_TEXT ?? "Jリーグ試合予想AI";
const startupTimeoutMs = Number(process.env.STREAMLIT_STARTUP_TIMEOUT_MS ?? 180_000);

if (!appUrl) {
  throw new Error("STREAMLIT_APP_URL is required");
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let ready = false;
let wakeClicks = 0;

async function visibleTextFromAllFrames() {
  const texts = [];
  for (const frame of page.frames()) {
    try {
      texts.push(await frame.locator("body").innerText({ timeout: 5_000 }));
    } catch {
      // Frames can be replaced while Streamlit starts. The next poll sees the new frame.
    }
  }
  return texts.join("\n");
}

try {
  console.log(`Opening ${appUrl}`);
  await page.goto(appUrl, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });

  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    const wakeButton = page.getByRole("button", {
      name: "Yes, get this app back up!",
    });

    if (await wakeButton.isVisible().catch(() => false)) {
      console.log("The app is asleep. Requesting a wake-up.");
      try {
        await wakeButton.click({ timeout: 10_000 });
        wakeClicks += 1;
      } catch {
        // The sleep page can disappear between the visibility check and the click.
      }
    }

    const visibleText = await visibleTextFromAllFrames();
    if (visibleText.includes(expectedText)) {
      ready = true;
      break;
    }

    await page.waitForTimeout(3_000);
  }

  if (!ready) {
    throw new Error(
      `The Streamlit app did not display ${JSON.stringify(expectedText)} within ${startupTimeoutMs}ms`,
    );
  }

  console.log(
    `Streamlit app is ready (${wakeClicks === 0 ? "already awake" : `wake clicks: ${wakeClicks}`}).`,
  );
} catch (error) {
  await mkdir("artifacts", { recursive: true });
  await page
    .screenshot({ path: "artifacts/streamlit-monitor-failure.png", fullPage: true })
    .catch(() => undefined);
  console.error(error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
