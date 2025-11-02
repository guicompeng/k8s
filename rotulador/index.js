const http = require('http');
const fs = require('fs');
const path = require('path');

const TARGET = 'http://10.187.36.245:30080/sample-page/';
const OUT = path.join(__dirname, 'rotulos.csv');
const INTERVAL_MS = 1000;
const HEALTHY_THRESHOLD_MS = 3000;

// garante cabeçalho
if (!fs.existsSync(OUT) || fs.statSync(OUT).size === 0) {
    fs.writeFileSync(OUT, 'timestamp;healthy\n');
}

function writeLine(healthy) {
    const line = `${new Date().toISOString()};${healthy}\n`;
    fs.appendFile(OUT, line, err => {
        if (err) console.error('Erro ao gravar CSV:', err.message);
    });
}

function ping() {
    const start = Date.now();
    const req = http.get(TARGET, (res) => {
        const elapsed = Date.now() - start;
        const okStatus = res.statusCode >= 200 && res.statusCode < 300;
        const healthy = okStatus && elapsed < HEALTHY_THRESHOLD_MS;
        writeLine(healthy);
        // descartar corpo
        res.resume();
    });

    // marca como unhealthy se não responder rapidamente
    req.setTimeout(HEALTHY_THRESHOLD_MS, () => {
        req.abort();
        writeLine(false);
    });

    req.on('error', () => writeLine(false));
}

// rodar imediatamente e depois a cada 1s
ping();
setInterval(ping, INTERVAL_MS);

// captura Ctrl+C para saída limpa
process.on('SIGINT', () => {
    console.log('\nEncerrando.');
    process.exit(0);
});