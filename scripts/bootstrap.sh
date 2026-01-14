#!/bin/bash
# Bootstrap TutorDex Development Environment
#
# This script sets up all required dependencies for local development.
# Run this once before starting development work.

set -e  # Exit on error

echo "🚀 Bootstrapping TutorDex development environment..."
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print success
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Function to print warning
warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to print error
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
echo "📦 Checking prerequisites..."
echo ""

if ! command_exists docker; then
    error "Docker is required but not installed"
    echo "   Please install Docker Desktop: https://www.docker.com/get-started"
    exit 1
fi
success "Docker found"

if ! command_exists docker-compose; then
    error "docker-compose is required but not installed"
    echo "   Please install docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi
success "docker-compose found"

if ! command_exists python3; then
    error "Python 3 is required but not installed"
    exit 1
fi
success "Python 3 found ($(python3 --version))"

if ! command_exists node; then
    warn "Node.js not found - required for website development"
    echo "   Install from: https://nodejs.org/"
else
    success "Node.js found ($(node --version))"
fi

echo ""
echo "📝 Checking .env files..."
echo ""

# Check for .env files
if [ ! -f "TutorDexAggregator/.env" ]; then
    warn "TutorDexAggregator/.env not found"
    echo "   Copy from .env.example: cp TutorDexAggregator/.env.example TutorDexAggregator/.env"
fi

if [ ! -f "TutorDexBackend/.env" ]; then
    warn "TutorDexBackend/.env not found"
    echo "   Copy from .env.example: cp TutorDexBackend/.env.example TutorDexBackend/.env"
fi

if [ ! -f "TutorDexWebsite/.env" ]; then
    warn "TutorDexWebsite/.env not found"
    echo "   Copy from .env.example: cp TutorDexWebsite/.env.example TutorDexWebsite/.env"
fi

echo ""
echo "🔧 Starting core services..."
echo ""

# Start Supabase (if present)
if [ -d "supabase" ]; then
    echo "Starting Supabase..."
    cd supabase
    docker-compose up -d
    cd ..
    
    # Wait for Supabase to be ready
    echo "⏳ Waiting for Supabase..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:54321/rest/v1/ > /dev/null 2>&1; then
            success "Supabase ready"
            break
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        error "Supabase failed to start"
        exit 1
    fi
else
    warn "Supabase directory not found - skipping"
fi

echo ""

# Start Redis
echo "Starting Redis..."
if docker ps -a | grep -q tutordex-redis; then
    docker start tutordex-redis
    success "Redis started (existing container)"
else
    docker run -d --name tutordex-redis -p 6379:6379 redis:7-alpine
    success "Redis started (new container)"
fi

echo ""

# Start observability stack
if [ -d "observability" ]; then
    echo "Starting observability stack (Prometheus, Grafana, Tempo)..."
    cd observability
    docker-compose up -d
    cd ..
    success "Observability stack started"
else
    warn "observability directory not found - skipping"
fi

echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
echo ""

if [ -f "TutorDexAggregator/requirements.txt" ]; then
    echo "Installing aggregator dependencies..."
    pip3 install -q -r TutorDexAggregator/requirements.txt
    success "Aggregator dependencies installed"
fi

if [ -f "TutorDexBackend/requirements.txt" ]; then
    echo "Installing backend dependencies..."
    pip3 install -q -r TutorDexBackend/requirements.txt
    success "Backend dependencies installed"
fi

echo ""

# Install Node.js dependencies (if Node is available)
if command_exists npm && [ -d "TutorDexWebsite" ]; then
    echo "📦 Installing website dependencies..."
    cd TutorDexWebsite
    npm install
    cd ..
    success "Website dependencies installed"
fi

echo ""
echo "💡 LLM API Check..."
echo ""

# Check if LLM API is running
if curl -s http://localhost:1234/v1/models > /dev/null 2>&1; then
    success "LLM API detected at http://localhost:1234"
else
    warn "LLM API not detected at http://localhost:1234"
    echo "   TutorDex can run without LLM for some operations"
    echo "   For full functionality, start LM Studio or compatible API"
fi

echo ""
echo "🎉 Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Review and configure .env files in each service"
echo "  2. Run database migrations: python scripts/migrate.py"
echo "  3. Start services: docker-compose up"
echo ""
echo "Access points:"
echo "  - Backend API: http://localhost:8000"
echo "  - Grafana: http://localhost:3300 (admin/admin)"
echo "  - Prometheus: http://localhost:9090"
echo "  - Tempo: http://localhost:3200"
echo "  - Supabase: http://localhost:54321"
echo ""
