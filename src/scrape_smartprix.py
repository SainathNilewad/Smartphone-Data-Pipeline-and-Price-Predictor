import json
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


# Broader listing URL: excludes upcoming phones but includes out-of-stock phones.
URL = "https://www.smartprix.com/mobiles/exclude_upcoming-stock"

LOAD_MORE = "div.sm-load-more"
CARD = "div.sm-product.has-features"

OUT_DIR = Path("data/raw")

MAX_STALLED_CLICKS = 4
PAGE_WAIT = 15
DELAY_SECONDS = 1.5
CHECKPOINT_EVERY = 25


def count_cards(driver):
    """Count phone cards currently loaded in the browser."""
    return len(driver.find_elements(By.CSS_SELECTOR, CARD))


def find_load_more(driver):
    """Find a visible Load More element."""
    for element in reversed(
        driver.find_elements(By.CSS_SELECTOR, LOAD_MORE)
    ):
        try:
            if element.is_displayed():
                return element
        except StaleElementReferenceException:
            continue

    return None


def save_html(driver, path):
    """Save the current rendered page."""
    path.write_text(driver.page_source, encoding="utf-8")
    print(f"HTML saved: {path}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, PAGE_WAIT)

    clicks = 0
    stalled = 0
    stop_reason = "Not started"

    try:
        print(f"Opening: {URL}")
        driver.get(URL)

        try:
            wait.until(
                lambda d: count_cards(d) > 0
            )
        except TimeoutException:
            stop_reason = (
                "No phone cards loaded. Check the URL and CARD selector."
            )
            print(stop_reason)
            return

        print(f"Initial phone cards: {count_cards(driver)}")

        while stalled < MAX_STALLED_CLICKS:
            before = count_cards(driver)

            button = find_load_more(driver)

            if button is None:
                stop_reason = "No visible Load More element"
                print(stop_reason)
                break

            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});",
                    button,
                )
                time.sleep(0.5)

                # Re-find the element in case the page updated.
                button = find_load_more(driver)

                if button is None:
                    stop_reason = "Load More element disappeared"
                    print(stop_reason)
                    break

                # Trigger the click on the current element.
                driver.execute_script(
                    "arguments[0].click();",
                    button,
                )

                try:
                    wait.until(
                        lambda d: count_cards(d) > before
                    )
                except TimeoutException:
                    # Count cards below to determine whether the
                    # click actually loaded anything.
                    pass

                after = count_cards(driver)
                clicks += 1

                added = after - before

                print(
                    f"Click {clicks}: {before} -> {after} cards "
                    f"(added {max(added, 0)})"
                )

                if added <= 0:
                    stalled += 1
                    print(
                        f"No new cards: "
                        f"{stalled}/{MAX_STALLED_CLICKS}"
                    )
                else:
                    stalled = 0

                    # Save a checkpoint after every 25 successful clicks.
                    if clicks % CHECKPOINT_EVERY == 0:
                        checkpoint_path = (
                            OUT_DIR / "smartprix_checkpoint.html"
                        )
                        save_html(driver, checkpoint_path)

                time.sleep(DELAY_SECONDS)

            except (
                StaleElementReferenceException,
                ElementClickInterceptedException,
                IndexError,
            ) as exc:
                stalled += 1
                print(
                    f"Click failed: {exc}. "
                    f"Stalled attempts: {stalled}/"
                    f"{MAX_STALLED_CLICKS}"
                )

        if stalled >= MAX_STALLED_CLICKS:
            stop_reason = (
                "Stopped after consecutive attempts added no new cards"
            )

    except KeyboardInterrupt:
        stop_reason = "Stopped manually by user"
        print("\nManual stop requested. Saving current page...")

    finally:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        html_path = OUT_DIR / f"smartprix_{timestamp}.html"
        meta_path = OUT_DIR / f"smartprix_{timestamp}.json"

        try:
            total_cards = count_cards(driver)
            save_html(driver, html_path)

            metadata = {
                "source": URL,
                "scraped_at": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "phone_cards": total_cards,
                "load_more_clicks": clicks,
                "stalled_clicks": stalled,
                "stop_reason": stop_reason,
                "html_file": html_path.name,
            }

            meta_path.write_text(
                json.dumps(metadata, indent=2),
                encoding="utf-8",
            )

            print("\nScraping finished.")
            print(f"Total loaded phone cards: {total_cards}")
            print(f"Load More clicks: {clicks}")
            print(f"Stop reason: {stop_reason}")
            print(f"HTML file: {html_path}")
            print(f"Metadata file: {meta_path}")

        except Exception as exc:
            print(f"Could not save final output: {exc}")

        finally:
            driver.quit()


if __name__ == "__main__":
    main()