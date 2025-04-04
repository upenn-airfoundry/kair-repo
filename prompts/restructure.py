import tiktoken

def truncate_text_to_token_limit(text, token_limit=128000):
    """
    Truncates a text string to a specified token limit using tiktoken.

    Args:
        text (str): The text string to truncate.
        token_limit (int): The maximum number of tokens allowed.

    Returns:
        str: The truncated text string.
    """

    encoding = tiktoken.get_encoding("cl100k_base")  # or another appropriate encoding
    tokens = encoding.encode(text)

    if len(tokens) <= token_limit:
        return text  # No truncation needed

    truncated_tokens = tokens[:token_limit]
    truncated_text = encoding.decode(truncated_tokens)
    return truncated_text

# Table of tag --> entity type, field, assessment criterion

