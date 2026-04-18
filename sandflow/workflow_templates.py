from __future__ import annotations

from .models import (
    ArtifactOutputDefinition,
    InputFieldDefinition,
    OutputFieldDefinition,
    WorkflowDefinition,
)


def starter_workflow_definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="review-document",
        name="Review Document",
        description="Review an uploaded document and produce structured findings plus a file artifact.",
        is_active=True,
        prompt="Review the provided document and produce a concise executive summary as well as generate a powerpoint artifact",
        input_fields=[
            InputFieldDefinition(
                id="document",
                label="Document",
                type="file",
                required=True,
                help_text="Upload a PDF, DOCX, TXT, or Markdown file.",
            ),
        ],
        output_fields=[
            OutputFieldDefinition(
                id="summary",
                label="Summary",
                type="markdown",
                required=True,
                help_text="A short executive summary.",
            ),
        ],
        artifact_outputs=[
            ArtifactOutputDefinition(
                id="report_file",
                label="Report File",
                format="pptx",
                required=True,
                help_text="Powerpoint report of review",
            )
        ],
    )
