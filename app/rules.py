"""Rules and Privacy Policy (/about and /privacy in the bot, Rules / Privacy in the app).

Цифры (доля призового фонда, лимит, минимальный вывод, название монеты) подставляются из текущих настроек,
чтобы текст всегда совпадал с тем, как работает сервис. При существенной правке текста меняйте REVISION —
тогда игроки снова увидят экран принятия.
"""
from . import settings

REVISION = "2026-11-24"

RULES = """<b>TonCry — Rules of the Service</b>
<i>Revision of {date}</i>

<b>1. General</b>
1.1. These Rules govern the use of TonCry (the “Service”), available in Telegram as the bot {bot} and its mini app.
1.2. The Service is an <b>entertainment game</b> — a mining simulator — intended solely for leisure.
1.3. The Service is not an investment platform, exchange, currency exchange office, wallet, mining or other financial service. It does not accept deposits, does not pay interest or investment returns, and does not buy back or exchange its in-game currency.
1.4. By tapping “I accept” and using the Service, the user (the “User”) confirms they have read and accept these Rules and the Privacy Policy. A User who does not agree must stop using the Service.
1.5. The Service is for persons aged 18 and over.

<b>2. Definitions</b>
2.1. <b>{coin}</b> — the Service’s in-game currency.
2.2. <b>Game server</b> — a virtual game item that accrues {coin} under the game rules.
2.3. <b>Game balance</b> — the amount of {coin} recorded for the User.
2.4. <b>Storage</b> — the game mechanism that accumulates accrued {coin} until the User collects them.
2.5. <b>Check</b> — a feature for giving {coin} to another user.
2.6. <b>Rewards Program</b> — the weekly prize program described in Section 7.

<b>3. In-game currency {coin}</b>
3.1. {coin} are used <b>only inside the game</b>: to rent, upgrade and renew Game servers, buy skins and other game features.
3.2. {coin} <b>are not</b> a cryptocurrency, token, digital financial asset, e-money or security. They are not issued on any blockchain and are not traded on any exchange.
3.3. {coin} <b>are not related to Toncoin (TON) or any other token</b>, despite the similarity of the name.
3.4. <b>{coin} cannot be exchanged, redeemed or withdrawn</b> for money, Toncoin or any other asset. The Service does not pay any monetary equivalent for them.
3.5. The Game balance is a record in the Service’s database reflecting game progress. The Service may change how {coin} are accrued and used.

<b>4. Game servers</b>
4.1. Game servers are <b>virtual game items</b>, not a rental of real hardware.
4.2. <b>No real cryptocurrency mining takes place.</b> {coin} are accrued by the game mechanics.
4.3. A Game server is rented for 30 days. Its {coin} output varies randomly from hour to hour (from 50% to 150% of its base rate). Accrued {coin} are in-game coins only: they have no monetary value and do not entitle the User to any payment. Game servers can be upgraded and renewed; their number is limited and restocked daily.
4.4. The Service withholds a game fee of 15% of accrued {coin}. The fee can be disabled on the terms shown in the Service.
4.5. Accrued {coin} collect in Storage for up to 24 hours; the User collects them by tapping “Claim”.

<b>5. Purchases</b>
5.1. Game features can be bought with Telegram Stars, Toncoin (TON) via a connected wallet (TON Connect), or {coin}. The User can also buy {coin} with TON.
5.2. A purchase is payment for digital entertainment content. It is not an investment or deposit and creates no right to any return.
5.3. Refunds are made at the Service’s discretion and as required by Telegram’s rules for Telegram Stars payments (/paysupport).

<b>6. Checks</b>
6.1. Users may give {coin} to other users with Checks inside Telegram.
6.2. Selling {coin} or accounts for money, crypto or other consideration is prohibited; the Service takes no part in such deals.

<b>7. Rewards Program</b>
7.1. Each week (Monday 00:00 to Monday 00:00, Moscow time) the Service sets aside a <b>prize fund equal to {share}% of the Service’s revenue for that week</b>.
7.2. The fund is shared among eligible Users in proportion to their game activity — the {coin} they collected with “Claim” during the week, <b>counted at their servers’ base rate</b>, so random fluctuations of output do not affect rewards. One User receives no more than <b>{cap} TON</b> per week. Unallocated funds are not paid out.
7.3. To be eligible, the User must have rented at least one Game server with a payment.
7.4. Rewards are credited in Toncoin (TON) to the User’s rewards balance after the week ends. The User may request a payout of the rewards balance to a TON wallet; the minimum is {min_wd} TON. Requests are reviewed manually.
7.5. <b>A reward is a prize for game activity, not income or a return on purchases.</b> Its size depends on the fund and other players’ activity and <b>is not guaranteed</b>; it may be zero in a given week.
7.6. The Service may change the fund share, the limit and the Program terms, or suspend or end the Program, by updating these Rules. Rewards already credited remain available for payout.
7.7. The Service may decline a payout request or cancel rewards obtained in violation of these Rules (Section 9).

<b>8. No income</b>
8.1. <b>The Service is not a way to earn money</b> and does not promise any income, money or cryptocurrency.
8.2. Accrual of {coin} is a game mechanic, not income.
8.3. Spend on the game only what you are willing to spend on entertainment. TON transactions are irreversible; the Service is not liable for an incorrect wallet address entered by the User.

<b>9. Restrictions</b>
9.1. It is prohibited to exploit bugs or vulnerabilities, create multiple accounts for bonuses or rewards, use automation, or sell {coin} or accounts.
9.2. If these Rules are violated, the Service may restrict access, freeze the Game balance and rewards balance, and decline payout requests.

<b>10. Changes</b>
10.1. The Service may change these Rules, prices and game parameters. The current version is available in the app (Rules) and via /about. Users will be asked to accept a materially changed version.

<b>11. Support</b>
11.1. Support is available right in the bot: send a message to {bot} or use Support in the app."""

PRIVACY = """<b>TonCry — Privacy Policy</b>
<i>Revision of {date}</i>

<b>1. About</b>
This policy explains what data the TonCry service (the bot {bot} and its mini app) processes and why. Questions about your data: write to support right in the bot.

<b>2. Data we receive</b>
<b>From Telegram:</b> your Telegram user ID, first name and username (if set). We do not receive your phone number, contacts, photos or messages with other people.
<b>Game data:</b> {coin} balance, Game servers and rental terms, skins, purchase history (item, payment method, time), Telegram Stars payment IDs and TON transaction hashes, Checks you sent and received, who invited you, completed tasks, weekly activity in the Rewards Program, rewards balance and payout requests (amount and the TON wallet address you entered), the time you accepted the Rules, and tutorial status.
<b>Support:</b> the messages you send to support and our replies.
<b>Technical:</b> the web server may keep standard technical logs (IP address, time, requested page) for up to 14 days for security. The app itself does not log your IP address.
<b>On your device</b> (inside Telegram, not sent to us): tutorial status and your TON Connect wallet connection.

<b>3. Why we use it</b>
• to run the game: accruals, purchases, Checks, the Rewards Program and payouts;
• to send notifications in the bot (storage full, rental ended, weekly rewards, payout decisions, support replies);
• to prevent abuse (multiple accounts, automation) and keep the Service secure;
• to answer support requests and resolve payment issues.
We do not sell your data and do not use it for advertising.

<b>4. Who receives data</b>
• <b>Telegram</b> — the platform the Service runs on, including Telegram Stars payments, under Telegram’s own privacy policy.
• <b>TON blockchain</b> — if you pay in Toncoin or receive a payout, the transaction (wallet addresses, amount, comment) is public and permanent. Payment comments contain a random code, not your personal data.
• <b>Wallets via TON Connect</b> (Tonkeeper, Telegram Wallet, etc.) — connection and signing happen in the wallet app under its rules.
• <b>Technical services</b> — when the app opens, it loads fonts (Google Fonts) and scripts (telegram.org, unpkg.com), which see your IP address as with any website. Our server uses toncenter.com and tonapi.io only for the Service’s own wallet and the TON rate; your data is not sent to them.
• <b>BotoHub</b> (botohub.me) — when you open the Missions tab, your Telegram user ID is sent to BotoHub to show sponsor tasks and check your subscriptions. No other data is sent.
• <b>Other players</b> see your first name only if you invited them or they claimed your Check.
• <b>Authorities</b> — only where required by law.

<b>5. Retention and deletion</b>
We keep data while you use the Service. The /deletedata command removes your first name and username. To delete your whole account, write to support. Records of payments and payouts are kept for up to 3 years to resolve disputes, without your name.

<b>6. Security</b>
Only Service administrators have access to the data. The Service runs over HTTPS, and data files are accessible only to the Service.

<b>7. Changes</b>
The current version is always available in the app (Privacy) and via /privacy. Material changes will be announced in the bot."""


def _fmt(doc: str, bot_username: str) -> str:
    from . import rewards
    return (PRIVACY if doc == "privacy" else RULES).format(
        date=REVISION, coin=settings.coin(), bot=f"@{bot_username}" if bot_username else "TonCry",
        share=f"{rewards.share() * 100:g}", cap=f"{rewards.cap():g}", min_wd=f"{settings.min_withdraw():g}")


def text(lang: str = "en", bot_username: str = "", doc: str = "rules") -> str:
    return _fmt(doc, bot_username)


def chunks(lang: str = "en", bot_username: str = "", limit: int = 3800, doc: str = "rules") -> list[str]:
    """Для Telegram: сообщения до 4096 символов, режем по разделам."""
    parts, cur = [], ""
    for block in text(lang, bot_username, doc).split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts
