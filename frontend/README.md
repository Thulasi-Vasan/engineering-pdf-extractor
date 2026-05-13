# Engineering PDF Extractor Frontend

A professional, engineering-grade dashboard for the Engineering PDF Extraction system. Built with React, TypeScript, Vite, and Tailwind CSS v4.

## Features

- **Dashboard Layout**: Professional dual-pane interface for configuration and result viewing.
- **Advanced Extraction Options**: Configure LLM and Vision processing with specific model selection.
- **Real-time Status**: Live server connectivity monitoring and multi-step extraction progress tracking.
- **Rich Result Viewer**: Syntax-highlighted JSON viewer, artifact browser, and detailed warning logs.
- **Run History**: Local persistence of recent extraction runs for quick reference.

## Tech Stack

- **Framework**: React 19 (TypeScript)
- **Build Tool**: Vite 6
- **Styling**: Tailwind CSS v4
- **Icons**: Lucide React
- **Animations**: Framer Motion
- **Runtime**: Bun

## Getting Started

### Prerequisites

- [Bun](https://bun.sh/) installed on your machine.

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   bun install
   ```

### Development

Start the development server:
```bash
bun run dev
```

The application will be available at `http://localhost:5173`.

### Production Build

Create an optimized production build:
```bash
bun run build
```

The output will be in the `dist/` directory.

## Linting & Quality

The project uses ESLint with React-specific plugins for high code quality:
- `eslint-plugin-react-x`
- `eslint-plugin-react-dom`
- `typescript-eslint`

Run the linter:
```bash
bun run lint
```

## Backend Integration

The frontend connects to the backend at `http://127.0.0.1:8000` by default. You can modify this in `src/lib/api.ts`.
