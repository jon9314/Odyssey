# Stage 1: Build the React application
FROM node:18-alpine AS build-stage

# Set the working directory in the container for the build stage
WORKDIR /app/frontend

# Copy package.json and package-lock.json (or yarn.lock)
COPY package*.json ./

# Install dependencies
# Using npm ci for cleaner installs if package-lock.json is present and reliable
RUN npm ci

# Copy the rest of the frontend application source code
COPY . .

# Build the application for production (Vite specific)
# This creates a 'dist' folder with static assets.
RUN npm run build

# Stage 2: Serve the static assets using a lightweight web server (nginx)
# This is a common pattern for production React builds.
# For development, docker-compose.yml will likely mount the source
# and run the dev server (e.g., `npm run dev`).
# This Dockerfile provides a production-ready image if needed directly.
# However, the current plan step in docker-compose.yml is to run the dev server.
# So, this nginx stage is more for a future production build.
# For the dev server setup as per docker-compose plan, we might only need up to npm install
# and then run `npm run dev`.

# Let's create a Dockerfile that primarily serves the dev environment as per current plan,
# but keep the build stage commented out for easy activation for production builds.

# Using Node image for development server
FROM node:18-alpine AS development-stage
# FROM node:20-slim AS development-stage # Alternative newer Node version

ENV NODE_ENV development

WORKDIR /app/frontend

COPY package*.json ./

# Install dependencies (could also use npm ci if lock file is robust)
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port Vite's dev server runs on (default is 5173)
# Or if you configure package.json script to use 3000, expose that.
EXPOSE 5173

# Command to run the Vite development server
# "--host" makes it accessible from outside the container (e.g., from Docker host)
CMD ["npm", "run", "dev", "--", "--host"]

# --- Production Build Stage (Example - keep commented or separate Dockerfile.prod) ---
# FROM node:18-alpine AS build
# WORKDIR /app/frontend
# COPY package*.json ./
# RUN npm ci
# COPY . .
# RUN npm run build

# FROM nginx:stable-alpine AS production-stage
# COPY --from=build /app/frontend/dist /usr/share/nginx/html
# # Copy a custom nginx config if needed:
# # COPY nginx.conf /etc/nginx/conf.d/default.conf
# EXPOSE 80
# CMD ["nginx", "-g", "daemon off;"]
```
