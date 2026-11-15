import type { NextConfig } from 'next';
const config:NextConfig={output:'standalone',devIndicators:false,async headers(){return [{source:'/backgrounds/:path*',headers:[{key:'Cache-Control',value:'public, max-age=31536000, immutable'}]}];},async rewrites(){return [{source:'/api/:path*',destination:`${process.env.API_INTERNAL_URL||'http://127.0.0.1:8000'}/api/:path*`}];}};
export default config;
