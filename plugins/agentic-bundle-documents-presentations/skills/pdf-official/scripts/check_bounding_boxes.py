from dataclasses import dataclass
import json
import sys


# Script to check that the `fields.json` file that Claude creates when analyzing PDFs
# does not have overlapping bounding boxes. See forms.md.

MAX_MESSAGES = 20
DEFAULT_FONT_SIZE = 14


@dataclass
class RectAndField:
    rect: list[float]
    rect_type: str
    field: dict


def _add_message_and_check_limit(messages: list[str], message: str) -> bool:
    """
    Adds a message to the list and checks if the maximum message limit has been reached.
    If the limit is reached, an abort message is added, and True is returned.
    """
    messages.append(message)
    if len(messages) >= MAX_MESSAGES:
        messages.append("Aborting further checks; fix bounding boxes and try again")
        return True
    return False


# Returns a list of messages that are printed to stdout for Claude to read.
def get_bounding_box_messages(fields_json_stream) -> list[str]:
    messages = []
    fields = json.load(fields_json_stream)
    messages.append(f"Read {len(fields['form_fields'])} fields")

    """
    Checks for overlapping bounding boxes and insufficient entry box height in a fields.json file.

    Args:
        fields_json_stream: A file-like object containing the fields.json data.

    Returns:
        A list of messages detailing any issues found or a success message.
    """

    def rects_intersect(r1: list[float], r2: list[float]) -> bool:
        """Checks if two rectangles intersect."""
        # Rectangles are defined as [x1, y1, x2, y2]
        disjoint_horizontal = r1[0] >= r2[2] or r1[2] <= r2[0]  # r1.x1 >= r2.x2 or r1.x2 <= r2.x1
        disjoint_vertical = r1[1] >= r2[3] or r1[3] <= r2[1]    # r1.y1 >= r2.y2 or r1.y2 <= r2.y1
        return not (disjoint_horizontal or disjoint_vertical)

    rects_and_fields = []
    for f in fields["form_fields"]:
        rects_and_fields.append(RectAndField(f["label_bounding_box"], "label", f))
        rects_and_fields.append(RectAndField(f["entry_bounding_box"], "entry", f))

    has_error = False
    for i, ri in enumerate(rects_and_fields):
        # This is O(N^2); we can optimize if it becomes a problem (e.g., using a spatial index).
        for j in range(i + 1, len(rects_and_fields)):
            rj = rects_and_fields[j]
            if ri.field["page_number"] == rj.field["page_number"] and rects_intersect(ri.rect, rj.rect):
                has_error = True
                page_num = ri.field["page_number"]
                if ri.field is rj.field:
                    if _add_message_and_check_limit(messages,
                                                     f"FAILURE (Page {page_num}): intersection between label and entry bounding boxes for `{ri.field['description']}` ({ri.rect}, {rj.rect})"):
                        return messages
                else:
                    if _add_message_and_check_limit(messages,
                                                     f"FAILURE (Page {page_num}): intersection between {ri.rect_type} bounding box for `{ri.field['description']}` ({ri.rect}) and {rj.rect_type} bounding box for `{rj.field['description']}` ({rj.rect})"):
                        return messages
        if ri.rect_type == "entry":
            if "entry_text" in ri.field:
                font_size = ri.field["entry_text"].get("font_size", DEFAULT_FONT_SIZE)
                entry_height = ri.rect[3] - ri.rect[1]
                if entry_height < font_size:
                    has_error = True
                    page_num = ri.field["page_number"]
                    if _add_message_and_check_limit(messages,
                                                     f"FAILURE (Page {page_num}): entry bounding box height ({entry_height}) for `{ri.field['description']}` is too short for the text content (font size: {font_size}). Increase the box height or decrease the font size."):
                        return messages

    if not has_error:
        messages.append("SUCCESS: All bounding boxes are valid")
    return messages

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_bounding_boxes.py [fields.json]")
        sys.exit(1)
    # Input file should be in the `fields.json` format described in forms.md.
    with open(sys.argv[1]) as f:
        messages = get_bounding_box_messages(f)
    for msg in messages:
        print(msg)
