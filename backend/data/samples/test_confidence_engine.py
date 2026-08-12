"""
Quick manual check of stage 4 (confidence_engine) against the real sample
fastener PDF's parsed text. Simulates three kinds of LLM extraction output
(directly labeled, contextually inferred, hallucinated) to confirm all
three confidence levels classify correctly. Not a pytest suite — just a
fast sanity script, since the pipeline has no test framework yet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ on sys.path

from pipeline.confidence_engine import score_fields
from pipeline.input_handler import handle_input
from pipeline.types import ExtractedField, ExtractionResult

SAMPLE_PDF = Path(__file__).resolve().parent / "sample_fastener_spec.pdf"


def main() -> None:
    raw_doc = handle_input("pdf", str(SAMPLE_PDF))

    extraction = ExtractionResult(
        category="fasteners",
        fields=[
            ExtractedField(
                field_name="material",
                value="Stainless Steel 18-8 (A2)",
                source_snippet="Material: Stainless Steel 18-8 (A2)",
                found=True,
            ),
            ExtractedField(
                field_name="corrosion_resistant",
                value="Yes",
                source_snippet="Suitable for outdoor and corrosive environments.",
                found=True,
            ),
            ExtractedField(
                field_name="operating_temperature",
                value="-20C to 80C",
                source_snippet=None,
                found=True,
            ),
        ],
        raw_llm_response=None,
    )

    scored = score_fields(extraction, raw_doc)

    for f in scored:
        print(f"{f.field_name:24s} confidence={f.confidence_level:11s} evidence={f.evidence_type:20s} "
              f"is_ai_generated={f.is_ai_generated}")
        print(f"    value:            {f.value}")
        print(f"    source_snippet:   {f.source_snippet}")
        print(f"    inference_chain:  {f.inference_chain}")
        print()

    levels = {f.field_name: f.confidence_level for f in scored}
    assert levels["material"] == "high", levels
    assert levels["corrosion_resistant"] == "medium", levels
    assert levels["operating_temperature"] == "unverified", levels
    print("PASS: one HIGH, one MEDIUM, one UNVERIFIED field classified correctly.")


if __name__ == "__main__":
    main()
