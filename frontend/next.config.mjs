/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['192.168.198.1'],
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:5001/api/:path*",
      },
    ]
  },
}

export default nextConfig
