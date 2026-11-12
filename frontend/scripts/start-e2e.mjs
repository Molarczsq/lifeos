// Run the same standalone output used by Docker, without Next dev/HMR.
import {cp, access} from 'node:fs/promises';
import {spawn} from 'node:child_process';
await cp('.next/static','.next/standalone/.next/static',{recursive:true});
try{await access('public');await cp('public','.next/standalone/public',{recursive:true});}catch(error){if(error.code!=='ENOENT')throw error;}
const child=spawn(process.execPath,['.next/standalone/server.js'],{stdio:'inherit',env:{...process.env,PORT:process.env.E2E_PORT||'3000',HOSTNAME:'0.0.0.0'}});
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill(signal));
child.on('exit',code=>process.exit(code??1));
