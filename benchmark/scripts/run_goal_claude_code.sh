#!/bin/bash
# Track 2A: Run /goal benchmark via Claude Code (Claude models only)
#
# Usage: ./run_goal_claude_code.sh [opus|sonnet|haiku]

set -euo pipefail

MODELS=("opus" "sonnet" "haiku")
GOAL="Find and fix all bugs in target_project/. After each fix, run: pytest bugs_manifest_tests/ -v && pytest target_project/tests/test_app.py -v. Stop when all 8 manifest tests pass and all existing tests still pass. Do not modify any test files."
TOKEN_BUDGET="500K"
RESULTS_DIR="results/raw"
RUNS_PER_MODEL=3

if [ $# -ge 1 ]; then
    MODELS=("$1")
fi

mkdir -p "$RESULTS_DIR"

for model in "${MODELS[@]}"; do
    for run in $(seq 1 $RUNS_PER_MODEL); do
        echo ""
        echo "=== /goal with $model (run $run/$RUNS_PER_MODEL) ==="
        echo ""

        # Reset target project to buggy state
        git checkout -- target_project/

        RUN_ID="goal_claude_${model}_run${run}_$(date +%s)"
        OUTPUT_FILE="$RESULTS_DIR/${RUN_ID}.jsonl"

        # Run non-interactively with stream-json output
        claude -p "/goal $GOAL" \
            --model "$model" \
            --tokens "$TOKEN_BUDGET" \
            --output-format stream-json \
            --allowedTools "Read,Edit,Bash,Write" \
            --verbose \
            2>&1 | tee "$OUTPUT_FILE"

        # Capture final state
        echo ""
        echo "=== Results for $RUN_ID ==="
        pytest bugs_manifest_tests/ -v --tb=short > "$RESULTS_DIR/${RUN_ID}_manifest.txt" 2>&1 || true
        pytest target_project/tests/test_app.py -v --tb=short > "$RESULTS_DIR/${RUN_ID}_existing.txt" 2>&1 || true

        manifest_pass=$(grep -c "PASSED" "$RESULTS_DIR/${RUN_ID}_manifest.txt" || echo 0)
        echo "  Manifest tests passing: $manifest_pass/8"

        # Reset for next run
        git checkout -- target_project/
    done
done

echo ""
echo "=== All /goal runs complete ==="
