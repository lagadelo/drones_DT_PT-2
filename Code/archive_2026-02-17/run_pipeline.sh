#!/bin/bash
# Complete Fleet Simulator Pipeline: Build → Simulate → Analyze

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INPUT_CSV="${1:-scenarios.csv}"
OUTPUT_CSV="${2:-results.csv}"
GENERATE_PLOTS="${3:---plot}"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  FLEET SIMULATOR: Complete Experimental Pipeline${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Step 1: Verify input file exists
echo -e "\n${BLUE}[1/4]${NC} Checking input file..."
if [ ! -f "$INPUT_CSV" ]; then
    echo -e "${RED}✗ Error: Input file '$INPUT_CSV' not found${NC}"
    echo "Usage: $0 [input.csv] [output.csv] [--plot|--no-plot]"
    echo "Default: $0 scenarios.csv results.csv --plot"
    exit 1
fi
echo -e "${GREEN}✓${NC} Input file found: $INPUT_CSV"

# Step 2: Build simulator
echo -e "\n${BLUE}[2/4]${NC} Building simulator..."
if make clean > /dev/null 2>&1; then
    if make > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Simulator built successfully"
    else
        echo -e "${RED}✗ Build failed${NC}"
        make  # Re-run to show error
        exit 1
    fi
else
    echo -e "${RED}✗ Cleanup failed${NC}"
    exit 1
fi

# Step 3: Run simulation
echo -e "\n${BLUE}[3/4]${NC} Running simulation..."
if ./fleet_simulator "$INPUT_CSV" "$OUTPUT_CSV"; then
    echo -e "${GREEN}✓${NC} Simulation completed"
else
    echo -e "${RED}✗ Simulation failed${NC}"
    exit 1
fi

# Step 4: Analyze results
echo -e "\n${BLUE}[4/4]${NC} Analyzing results..."

if command -v python3 &> /dev/null; then
    
    python3 analyze_results.py "$OUTPUT_CSV"
    
    if [[ "$GENERATE_PLOTS" == "--plot" || "$GENERATE_PLOTS" == "-p" ]]; then
        if python3 -c "import matplotlib" 2>/dev/null; then
            echo ""
            python3 analyze_results.py "$OUTPUT_CSV" --plot
            PLOT_FILE="${OUTPUT_CSV%.csv}.png"
            if [ -f "$PLOT_FILE" ]; then
                echo -e "${GREEN}✓${NC} Plots saved to: $PLOT_FILE"
            fi
        else
            echo -e "${BLUE}ℹ${NC} Matplotlib not installed. Skipping plots."
            echo "   Install with: pip install matplotlib numpy"
        fi
    fi
    
    # Export JSON summary
    python3 analyze_results.py "$OUTPUT_CSV" --json > /dev/null 2>&1 && \
        echo -e "${GREEN}✓${NC} JSON summary created: ${OUTPUT_CSV%.csv}_summary.json" || true
else
    echo -e "${RED}✗ Python3 not found. Install Python3 to analyze results.${NC}"
fi

# Final summary
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PIPELINE COMPLETE${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Output files:"
echo "  • Results CSV: $OUTPUT_CSV"
echo "  • Plots:       ${OUTPUT_CSV%.csv}.png (if matplotlib installed)"
echo "  • Summary:     ${OUTPUT_CSV%.csv}_summary.json"
echo ""
echo "Next steps:"
echo "  • Review $OUTPUT_CSV in spreadsheet application"
echo "  • Check ${OUTPUT_CSV%.csv}.png for visualizations"
echo "  • Modify scenarios.csv and re-run pipeline"
echo ""
