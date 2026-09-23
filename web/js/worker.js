self.onmessage=e=>{const {type,rows}=e.data;if(type==='csv'){postMessage({csv:'\ufeffgid;role\n'+rows.map(x=>`${x.gid};${x.role||''}`).join('\n')})}};
