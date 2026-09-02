import unittest
from unittest.mock import MagicMock, patch

from src.automation import (
    BotConfig,
    get_access_mode,
    get_event_id,
    is_known_sector_url,
    resolve_target_url,
    select_preferred_sector,
)
from src.telegram_client import (
    get_latest_chat_id,
    send_telegram_message,
)


def make_sector(name: str, classes: str = "match_sector") -> MagicMock:
    row = MagicMock()
    name_locator = MagicMock()
    name_locator.inner_text.return_value = name
    row.locator.return_value = name_locator
    row.get_attribute.side_effect = lambda attribute: {
        "class": classes,
        "aria-disabled": None,
    }.get(attribute)
    row.is_enabled.return_value = True
    return row


class ConfigurationTests(unittest.TestCase):
    def test_builds_fla_id_url_from_event_id(self) -> None:
        self.assertEqual(
            resolve_target_url("39374", "fla_id"),
            (
                "https://ingressos.flamengo.com.br/member/sector"
                "?event=39374"
            ),
        )

    def test_builds_public_url_from_event_id(self) -> None:
        self.assertEqual(
            resolve_target_url("39374", "public"),
            (
                "https://ingressos.flamengo.com.br/buy/sector"
                "?event=39374&allow-blocked-member=1"
            ),
        )

    def test_rejects_short_monitor_interval(self) -> None:
        with self.assertRaises(ValueError):
            BotConfig(monitor_interval_seconds=10)

    def test_rejects_more_than_two_tickets(self) -> None:
        with self.assertRaises(ValueError):
            BotConfig(desired_quantity=3)

    def test_recognizes_current_and_legacy_sector_routes(self) -> None:
        self.assertEqual(
            get_access_mode(
                "https://ingressos.flamengo.com.br/buy/sector?event=1"
            ),
            "público geral",
        )
        self.assertEqual(
            get_access_mode(
                "https://ingressos.flamengo.com.br/member/sector?event=2"
            ),
            "Fla-ID",
        )
        self.assertEqual(
            get_event_id(
                "https://ingressos.flamengo.com.br/member/sector?event=2"
            ),
            "2",
        )
        self.assertEqual(
            get_access_mode(
                "https://ingressos.flamengo.com.br/member?event=3"
            ),
            "Fla-ID",
        )
        self.assertEqual(
            get_access_mode(
                "https://ingressos.flamengo.com.br/buy?event=4"
            ),
            "público geral",
        )

    def test_accepts_member_url_without_sector_suffix(self) -> None:
        url = "https://ingressos.flamengo.com.br/member?event=39374"
        self.assertEqual(resolve_target_url(url, "fla_id"), url)

    def test_fla_id_authentication_url_is_a_wait_state(self) -> None:
        authentication_url = (
            "https://flaid.flamengo.com.br/realms/flamengo/"
            "protocol/openid-connect/auth?client_id=ticketing"
        )

        self.assertFalse(is_known_sector_url(authentication_url))


class SectorSelectionTests(unittest.TestCase):
    def make_page(self, rows: list[MagicMock]) -> MagicMock:
        collection = MagicMock()
        collection.count.return_value = len(rows)
        collection.nth.side_effect = rows * 4
        page = MagicMock()
        page.locator.return_value = collection
        return page

    def test_uses_second_north_option_when_first_is_sold(self) -> None:
        north_sold = make_sector(
            "NORTE NÍVEL 1 | E",
            "match_sector sold",
        )
        north_available = make_sector("NORTE NÍVEL 2 | F")
        south_available = make_sector("SUL NÍVEL 1 | C")
        page = self.make_page(
            [north_sold, north_available, south_available]
        )

        selected = select_preferred_sector(page, log=lambda _: None)

        self.assertEqual(selected, "NORTE NÍVEL 2 | F")
        north_available.click.assert_called_once()
        south_available.click.assert_not_called()

    def test_falls_back_to_south_when_north_is_sold(self) -> None:
        north_sold = make_sector(
            "NORTE NÍVEL 1 | E",
            "match_sector sold",
        )
        south_available = make_sector("SUL NÍVEL 1 | C")
        page = self.make_page([north_sold, south_available])

        selected = select_preferred_sector(page, log=lambda _: None)

        self.assertEqual(selected, "SUL NÍVEL 1 | C")
        south_available.click.assert_called_once()


class TelegramTests(unittest.TestCase):
    @patch("src.telegram_client.urlopen")
    def test_finds_latest_chat_id(self, mocked_urlopen: MagicMock) -> None:
        response = mocked_urlopen.return_value.__enter__.return_value
        response.read.return_value = (
            b'{"ok":true,"result":[{"message":{"chat":{"id":123}}}]}'
        )

        self.assertEqual(get_latest_chat_id("token"), "123")

    @patch("src.telegram_client.urlopen")
    def test_sends_message(self, mocked_urlopen: MagicMock) -> None:
        response = mocked_urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"ok":true,"result":{}}'

        send_telegram_message("token", "123", "teste")

        mocked_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
