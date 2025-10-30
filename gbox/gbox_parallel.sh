#!/bin/bash

# Parallel GBOX runner - splits tasks evenly across 4 boxes using tmux
#
# Usage:
#   ./gbox_parallel.sh START END RESULT_DIR
#
# Example:
#   ./gbox_parallel.sh 0 100 results_run1
#
# To view progress:
#   tmux attach -t webarena_gbox

# Configuration
CONDA_ENV_NAME="webarena"
TMUX_SESSION="webarena_gbox"

# 4 GBOX box IDs
BOX_IDS=(
    "420081b1-5de0-417b-a905-7058c1ce0608"
    "d789bbec-453c-4091-b1ed-37d64d591a86"
    "a123c882-09e0-4148-aa86-599720846502"
    "b1a4bb98-6f00-4f1d-9751-82cd787cbe8c"
)

NUM_BOXES=${#BOX_IDS[@]}

# Parse arguments
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 START END RESULT_DIR"
    echo "Example: $0 0 812 results_run1"
    exit 1
fi

START=$1
END=$2
RESULT_DIR=$3

# Calculate task splits
TOTAL_TASKS=$((END - START))
TASKS_PER_BOX=$((TOTAL_TASKS / NUM_BOXES))
REMAINDER=$((TOTAL_TASKS % NUM_BOXES))

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  WebArena GBOX Parallel Runner                                       ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
echo "║  Tasks:       $START to $((END - 1)) (total: $TOTAL_TASKS)                                    ║"
echo "║  Boxes:       $NUM_BOXES boxes                                                  ║"
echo "║  Per Box:     ~$TASKS_PER_BOX tasks                                               ║"
echo "║  Result Dir:  $RESULT_DIR                                            ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"

# Kill existing session if it exists
tmux kill-session -t $TMUX_SESSION 2>/dev/null

# Create new tmux session with first window (detached)
tmux new-session -d -s $TMUX_SESSION -n "Box-0"

# Create additional windows for remaining boxes
for i in $(seq 1 $((NUM_BOXES - 1))); do
    tmux new-window -t $TMUX_SESSION -n "Box-$i"
done

# Function to run job in a specific window
run_job() {
    local window_id=$1
    local box_id=$2
    local task_start=$3
    local task_end=$4

    echo "Window $window_id: Box ${box_id:0:8}... tasks $task_start-$((task_end - 1))"

    tmux select-window -t $TMUX_SESSION:$window_id
    tmux send-keys "conda activate $CONDA_ENV_NAME" C-m
    sleep 1
    tmux send-keys "python gbox_run.py --start $task_start --end $task_end --box_id $box_id --result_dir $RESULT_DIR --provider bedrock" C-m
}

# Launch jobs on each window with evenly distributed tasks
current_start=$START
for i in $(seq 0 $((NUM_BOXES - 1))); do
    box_id=${BOX_IDS[$i]}

    # Calculate this box's task range
    tasks_for_this_box=$TASKS_PER_BOX

    # Give remainder tasks to first few boxes
    if [ $i -lt $REMAINDER ]; then
        tasks_for_this_box=$((tasks_for_this_box + 1))
    fi

    current_end=$((current_start + tasks_for_this_box))

    # Launch job
    run_job $i "$box_id" $current_start $current_end

    current_start=$current_end
    sleep 2
done

echo ""
echo "✅ All $NUM_BOXES boxes started in tmux session '$TMUX_SESSION'"
echo ""
echo "To view progress:"
echo "  tmux attach -t $TMUX_SESSION"
echo ""
echo "Navigation (once attached):"
echo "  Ctrl+B then 0-9     - Switch to window 0-9"
echo "  Ctrl+B then n       - Next window"
echo "  Ctrl+B then p       - Previous window"
echo "  Ctrl+B then w       - List all windows"
echo "  Ctrl+B then D       - Detach from tmux"
echo ""
echo "To kill all jobs:"
echo "  tmux kill-session -t $TMUX_SESSION"
echo ""

# Optionally attach to session immediately
read -p "Attach to tmux session now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    tmux attach -t $TMUX_SESSION
fi
