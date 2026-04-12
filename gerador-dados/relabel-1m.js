#!/usr/bin/env node

const fs = require('fs');
const readline = require('readline');

const inputPath = process.argv[2] || 'dataset-1m.csv';
const outputPath = process.argv[3] || 'dataset-1m-relabel.csv';
const lookback = 6;

if (!fs.existsSync(inputPath)) {
	console.error(`Arquivo nao encontrado: ${inputPath}`);
	process.exit(1);
}

const input = fs.createReadStream(inputPath, { encoding: 'utf8' });
const output = fs.createWriteStream(outputPath, { encoding: 'utf8' });

const rl = readline.createInterface({
	input,
	crlfDelay: Infinity,
});

let headerWritten = false;
let targetIndex = -1;
const buffer = [];

let rowsRead = 0;
let rowsChanged = 0;
let zeroRows = 0;

function flushOne() {
	const row = buffer.shift();
	output.write(`${row.cols.join(',')}\n`);
}

function toZero(row) {
	if (row.cols[targetIndex].trim() !== '0') {
		row.cols[targetIndex] = '0';
		rowsChanged += 1;
	}
}

rl.on('line', (line) => {
	if (!headerWritten) {
		const headerCols = line.split(',');
		targetIndex = headerCols.indexOf('target');

		if (targetIndex === -1) {
			console.error('Coluna target nao encontrada no CSV.');
			process.exitCode = 1;
			rl.close();
			input.destroy();
			output.end();
			return;
		}

		output.write(`${line}\n`);
		headerWritten = true;
		return;
	}

	if (!line.trim()) {
		return;
	}

	const cols = line.split(',');
	if (cols.length <= targetIndex) {
		return;
	}

	rowsRead += 1;
	const row = { cols };

	if (cols[targetIndex].trim() === '0') {
		zeroRows += 1;
		for (const prev of buffer) {
			toZero(prev);
		}
	}

	buffer.push(row);

	while (buffer.length > lookback) {
		flushOne();
	}
});

rl.on('close', () => {
	while (buffer.length > 0) {
		flushOne();
	}

	output.end(() => {
		console.log(`Entrada: ${inputPath}`);
		console.log(`Saida: ${outputPath}`);
		console.log(`Linhas processadas: ${rowsRead}`);
		console.log(`Linhas com target 0 encontradas: ${zeroRows}`);
		console.log(`Targets alterados para 0: ${rowsChanged}`);
	});
});

rl.on('error', (err) => {
	console.error('Erro ao ler arquivo:', err.message);
	process.exit(1);
});

output.on('error', (err) => {
	console.error('Erro ao escrever arquivo:', err.message);
	process.exit(1);
});
