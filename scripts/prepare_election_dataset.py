import argparse
import os
from pathlib import Path

import duckdb


DEFAULT_KEYWORDS = [
    "kamala", "harris", "trump",
    "democrat", "democrats",
    "republican", "republicans", "gop",
    "presiden", "election", "poll", "debate",
]


def export_tweets(args):
    # Decide whether we are reading from Hugging Face or from local parquet files
    if args.hf_dataset:
        from huggingface_hub import HfFileSystem
        
        fs = HfFileSystem(token=os.getenv("HF_TOKEN"))
        parquet_files = fs.glob(f"datasets/{args.hf_dataset}/**/*.parquet")

        if not parquet_files:
            raise FileNotFoundError(f"No parquet files found in {args.hf_dataset}")

        parquet_urls = []
        for file in parquet_files:
            relative_path = file.split(f"datasets/{args.hf_dataset}/", 1)[1]
            url = f"https://huggingface.co/datasets/{args.hf_dataset}/resolve/main/{relative_path}"
            parquet_urls.append("'" + url.replace("'", "''") + "'")

        source = f"read_parquet([{', '.join(parquet_urls)}])"
        source_name = f"huggingface://{args.hf_dataset}"

    else:
        input_path = Path(args.input).expanduser().resolve()

        if input_path.is_file() and input_path.suffix == ".parquet":
            source = f"read_parquet('{input_path}')"
            source_name = str(input_path)

        elif input_path.is_dir():
            parquet_files = list(input_path.rglob("*.parquet"))
            if not parquet_files:
                raise FileNotFoundError(f"No parquet files found under {input_path}")

            source = f"read_parquet('{input_path}/**/*.parquet')"
            source_name = str(input_path)

        
    con = duckdb.connect()

    # Look at the columns in the parquet files so the script can handle slightly different schemas
    columns = con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
    available_columns = {row[0] for row in columns}

    def use_column(possible_names, fallback="NULL"):
        for name in possible_names:
            if name in available_columns:
                return name
        return fallback

    timestamp_col = use_column(["date", "createdAt", "created_at", "timestamp"])
    text_col = use_column(["rawContent", "text", "full_text", "content"])

    
    lang_col = use_column(["lang", "language"])
    likes_col = use_column(["likeCount", "likes", "favorite_count"])
    retweets_col = use_column(["retweetCount", "retweets", "retweet_count"])
    replies_col = use_column(["replyCount", "replies", "reply_count"])
    quotes_col = use_column(["quoteCount", "quotes", "quote_count"])
    id_col = use_column(["id", "tweetId", "tweet_id"])
    username_col = use_column(["username", "user_name", "screen_name"])

    def sql_string(value):
        return "'" + value.replace("'", "''") + "'"

    filters = [
        f"CAST({timestamp_col} AS TIMESTAMP) >= CAST({sql_string(args.start)} AS TIMESTAMP)",
        f"CAST({timestamp_col} AS TIMESTAMP) < CAST({sql_string(args.end)} AS TIMESTAMP)",
        f"{text_col} IS NOT NULL",
        f"length(trim({text_col})) > 0",
    ]

    if args.lang:
        if lang_col == "NULL":
            raise ValueError("A language filter was requested, but no language column was found")
        filters.append(f"lower({lang_col}) = lower({sql_string(args.lang)})")

    if args.keywords:
        keyword_filters = []
        for keyword in args.keywords:
            keyword_filters.append(
                f"lower({text_col}) LIKE {sql_string('%' + keyword.lower() + '%')}"
            )
        filters.append("(" + " OR ".join(keyword_filters) + ")")

    limit = f"LIMIT {args.limit}" if args.limit else ""

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    query = f"""
    COPY (
        SELECT
            CAST({timestamp_col} AS TIMESTAMP) AS timestamp,
            {text_col} AS text,
            {sql_string(args.event_id)} AS event_id,
            TRY_CAST({likes_col} AS BIGINT) AS likes,
            TRY_CAST({retweets_col} AS BIGINT) AS retweets,
            TRY_CAST({replies_col} AS BIGINT) AS replies,
            TRY_CAST({quotes_col} AS BIGINT) AS quotes,
            CAST({id_col} AS VARCHAR) AS post_id,
            CAST({username_col} AS VARCHAR) AS username,
            CAST({lang_col} AS VARCHAR) AS lang
        FROM {source}
        WHERE {" AND ".join(filters)}
        ORDER BY timestamp
        {limit}
    ) TO '{out_path}' (HEADER, DELIMITER ',');
    """

    con.execute(query)

    with out_path.open("r", encoding="utf-8") as f:
        row_count = max(sum(1 for _ in f) - 1, 0)

    print(f"Saved {row_count} rows to {out_path}")
    print(f"Source: {source_name}")
    print(f"Date window: [{args.start}, {args.end})")
    print(f"Keywords: {', '.join(args.keywords) if args.keywords else 'none'}")


def main():
    parser = argparse.ArgumentParser(
        description="Export election tweets from parquet files into a clean CSV."
    )

    parser.add_argument("--input", help="Local parquet file or folder containing parquet files")
    parser.add_argument("--hf-dataset", help="Optional Hugging Face dataset id")
    parser.add_argument("--start", default="2024-10-01T00:00:00Z")
    parser.add_argument("--end", default="2024-12-01T00:00:00Z")
    parser.add_argument("--event-id", default="election_2024")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", default="data/raw/tweets_data.csv")

    args = parser.parse_args()

    if not args.input and not args.hf_dataset:
        raise ValueError("Provide either --input or --hf-dataset")

    export_tweets(args)


if __name__ == "__main__":
    main()
