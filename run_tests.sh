#!/bin/bash
# Test runner script for JolChobi

echo "🧪 Running JolChobi Test Suite..."
echo "=================================="

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing test dependencies..."
    pip install -r tests/requirements-test.txt
fi

# Run tests with coverage
echo ""
echo "📊 Running tests with coverage..."
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
    echo ""
    echo "📈 Coverage report generated in htmlcov/index.html"
    echo "   Open with: open htmlcov/index.html (macOS) or xdg-open htmlcov/index.html (Linux)"
else
    echo ""
    echo "❌ Some tests failed. Please review the output above."
    exit 1
fi
