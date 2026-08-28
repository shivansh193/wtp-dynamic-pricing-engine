/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // build a self-contained server bundle for the Docker image
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  },
};

module.exports = nextConfig;
