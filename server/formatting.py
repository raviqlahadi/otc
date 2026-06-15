from models import Question


def format_question(question: Question) -> str:
    """Format question as plain text: stem + 4 labeled options on separate lines."""
    return (
        f"{question.question_text}\n"
        f"A. {question.option_a}\n"
        f"B. {question.option_b}\n"
        f"C. {question.option_c}\n"
        f"D. {question.option_d}"
    )
