import re


def extract_structured_result(
    query: str,
    text: str
):

    q = query.lower()

    if "gold" in q:
        return extract_gold_price(text)

    if "score" in q or "ipl" in q:
        return extract_cricket_score(text)

    if "weather" in q:
        return extract_weather(text)

    return text


# -----------------------------
# GOLD PRICE
# -----------------------------

def extract_gold_price(text):

    price_pattern = re.compile(
        r'(\d{1,2}[,]?\d{3})'
    )

    prices = price_pattern.findall(text)

    if not prices:
        return text

    unique_prices = []

    for p in prices:

        if p not in unique_prices:

            unique_prices.append(p)

    output = []

    if len(unique_prices) >= 1:

        output.append(
            f"24K Gold: ₹{unique_prices[0]} / gram"
        )

    if len(unique_prices) >= 2:

        output.append(
            f"22K Gold: ₹{unique_prices[1]} / gram"
        )

    return "\n".join(output)


# -----------------------------
# CRICKET SCORE
# -----------------------------

def extract_cricket_score(text):

    score_pattern = re.compile(
        r'\d{1,3}/\d{1,2}'
    )

    scores = score_pattern.findall(text)

    if not scores:
        return text

    return f"Score: {scores[0]}"


# -----------------------------
# WEATHER
# -----------------------------

def extract_weather(text):

    temp_pattern = re.compile(
        r'\d{1,2}\s?°?C'
    )

    match = temp_pattern.search(text)

    if not match:
        return text

    return f"Temperature: {match.group()}"