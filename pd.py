import sigrokdecode as srd

__all__ = ['Decoder']

ir = {
	'0011': ['IDCODE', 32],
	'0111': ['PDICOM', 9],
	'1111': ['BYPASS', 1],
}

jedec_id = {
	0x1f: 'Atmel'
}

avr_idcode = {
	0x9642: 'ATXMega64A3U',
	0x9742: 'ATXMega128A3U',
	0x9744: 'ATXMega192A3U',
	0x9842: 'ATXMega256A3U',
}

def decode_device_id_code(bits):
	version = int(f'0b{bits[-32:-28]}', 2)
	part = int(f'0b{bits[-28:-12]}', 2)
	part = avr_idcode.get(part, f'{part:#x}')
	manufacturer = jedec_id.get(int(f'0b{bits[-12:-1]}', 2), 'INVALID')
	id_hex = '{:#x}'.format(int(f'0b{bits}', 2))
	return id_hex, manufacturer, version, part

class Annotations:
	'''Annotation and binary output classes.'''
	(
		JTAG_ITEM, JTAG_FIELD, JTAG_COMMAND, JTAG_WARNING,
		DATA_IN, PARITY_IN_OK, PARITY_IN_ERR,
		DATA_OUT, PARITY_OUT_OK, PARITY_OUT_ERR,
		BREAK, OPCODE, DATA_PROG, DATA_DEV,
		PDI_BREAK, ENABLE, DISABLE, COMMAND
	) = range(18)

	(
		PARITY_OK, PARITY_ERR
	) = range(2)
A = Annotations

class PDI:
	'''PDI protocol instruction opcodes, and operand formats.'''
	(
		OP_LDS, OP_LD, OP_STS, OP_ST,
		OP_LDCS, OP_REPEAT, OP_STCS, OP_KEY,
	) = range(8)

	pointer_format_nice = [
		'*(ptr)',
		'*(ptr++)',
		'ptr',
		'ptr++ (rsv)',
	]
	pointer_format_terse = [
		'*p',
		'*p++',
		'p',
		'(rsv)',
	]
	ctrl_reg_name = {
		0: 'status',
		1: 'reset',
		2: 'ctrl',
	}

class PDIDecoder:
	ann_class_text = {
		A.PARITY_OK: ['Parity OK', 'Par OK', 'P'],
		A.PARITY_ERR: ['Parity error', 'Par ERR', 'PE'],
		A.BREAK: ['Break condition', 'BREAK', 'BRK'],
	}

	ann_class = {
		A.DATA_IN : {
			A.PARITY_OK: A.PARITY_IN_OK,
			A.PARITY_ERR: A.PARITY_IN_ERR,
		},
		A.DATA_OUT : {
			A.PARITY_OK: A.PARITY_OUT_OK,
			A.PARITY_ERR: A.PARITY_OUT_ERR,
		},
	}

	special_character = {
		0xBB: 'BREAK',
		0xDB: 'DELAY',
		0xEB: 'EMPTY',
	}

	def __init__(self, decoder):
		self.decoder = decoder

	def putb(self, bit, dir, value):
		ann_class = PDIDecoder.ann_class[dir]
		self.decoder.putb(bit, [ann_class[value], PDIDecoder.ann_class_text[value]])

	def put_special(self, data, dir):
		special = PDIDecoder.special_character.get(data, 'INVALID')
		if dir == A.DATA_IN:
			self.decoder.putx([A.DATA_PROG, [special]])
		else:
			self.decoder.putx([A.DATA_DEV, [special]])

	def checkParity(self, value, dir):
		parity = int(value[0])
		data = int(f'0b{value[1:]}', 2)
		dataText = f'{data:#04x}'

		onesCount = sum(int(bit) for bit in value[1:])
		parityOK = (onesCount + parity) & 1 == 0

		# Protect ourselves from batshit PDI frames
		if len(value) != 9:
			return 0, False

		decoder = self.decoder
		decoder.putf(0, 7, [dir, [f'Data: {dataText}', f'D: {dataText}', dataText]])
		self.putb(8, dir, A.PARITY_OK if parityOK else A.PARITY_ERR)

		if not parityOK:
			self.put_special(data, dir)
		return data, parityOK

	def handleInput(self, value):
		data, parityOK = self.checkParity(value, A.DATA_IN)
		if not parityOK:
			return

	def handleOutput(self, value):
		data, parityOK = self.checkParity(value, A.DATA_OUT)
		if not parityOK:
			return

class Decoder(srd.Decoder):
	api_version = 3
	id = 'jtag_avr'
	name = 'JTAG / AVR'
	longname = 'Joint Test Action Group / Atmel AVR PDI'
	desc = 'Atmel AVR PDI JTAG protocol.'
	license = 'gplv2+'
	inputs = ['jtag']
	outputs = []
	tags = ['Debug/trace']
	annotations = (
		('item', 'Item'),
		('field', 'Field'),
		('command', 'Command'),
		('warning', 'Warning'),
		('data-in', 'PDI data in'),
		('parity-in-ok', 'Parity OK'),
		('parity-in-err', 'Parity error'),
		('data-out', 'PDI data out'),
		('parity-out-ok', 'Parity OK'),
		('parity-out-err', 'Parity error'),
		('break', 'BREAK condition'),
		('opcode', 'Instruction opcode'),
		('data-prog', 'Programmer data'),
		('data-dev', 'Device data'),
		('pdi-break', 'BREAK at PDI level'),
		('enable', 'Enable PDI'),
		('disable', 'Disable PDI'),
		('cmd-data', 'PDI command with data'),
	)
	annotation_rows = (
		('items', 'Items', (A.JTAG_ITEM,)),
		('fields', 'Fields', (A.JTAG_FIELD,)),
		('commands', 'Commands', (A.JTAG_COMMAND,)),
		('warnings', 'Warnings', (A.JTAG_WARNING,)),
		('data_in', 'PDI Data (In)', (A.DATA_IN, A.PARITY_IN_OK, A.PARITY_IN_ERR)),
		('data_out', 'PDI Data (Out)', (A.DATA_OUT, A.PARITY_OUT_OK, A.PARITY_OUT_ERR)),
		('data_fields', 'PDI Data Fields', (A.BREAK,)),
		('pdi_fields', 'PDI Fields', (A.OPCODE, A.PDI_BREAK)),
		('pdi_prog', 'PDI Programmer In', (A.DATA_PROG,)),
		('pdi_dev', 'PDI Device Out', (A.DATA_DEV,)),
		('pdi_cmds', 'PDI Commands', (A.ENABLE, A.DISABLE, A.COMMAND)),
	)

	def __init__(self):
		self.reset()
		self.pdi = PDIDecoder(self)

	def reset(self):
		self.state = 'IDLE'
		self.samplenums = None

	def start(self):
		self.out_ann = self.register(srd.OUTPUT_ANN)

	def putx(self, data):
		self.put(self.ss, self.es, self.out_ann, data)

	def putf(self, s, e, data):
		self.put(self.samplenums[s][0], self.samplenums[e][1], self.out_ann, data)

	def putb(self, b, data):
		self.putf(b, b, data)

	def handle_reg_bypass(self, cmd, bits):
		self.putx([A.JTAG_ITEM, [f'BYPASS: {bits}']])

	def handle_reg_idcode(self, cmd, bits):
		id_hex, manuf, vers, part = decode_device_id_code(bits)
		self.putb(0, [A.JTAG_FIELD, ['Reserved', 'Res', 'R']])
		self.putf(1, 11, [A.JTAG_FIELD, [f'Manufacturer: {manuf}', 'Manuf', 'M']])
		self.putf(12, 27, [A.JTAG_FIELD, [f'Part: {part}', 'Part', 'P']])
		self.putf(28, 31, [A.JTAG_FIELD, [f'Version: {vers}', 'Version', 'V']])

		self.putx([A.JTAG_ITEM, [f'IDCODE: {id_hex}']])
		self.putx([A.JTAG_COMMAND, [f'IDCODE: {id_hex} ({manuf}: {part}@r{vers})']])

	def decode(self, ss, es, data):
		self.ss, self.es = ss, es
		cmd, val = data

		if cmd != 'NEW STATE':
			val, self.samplenums = val
			self.samplenums.reverse()

		if cmd == 'IR TDI':
			self.state = ir.get(val[0:4], ['UNKNOWN', 0])[0]
			self.putx([2, [f'IR: {self.state}']])

		if self.state == 'BYPASS':
			if cmd != 'DR TDI':
				return
			self.handle_reg_bypass(cmd, val)
			self.state = 'IDLE'
		elif self.state in ('IDCODE'):
			if cmd != 'DR TDO':
				return
			handle_reg = getattr(self, f'handle_reg_{self.state.lower()}')
			handle_reg(cmd, val)
			self.state = 'IDLE'
		elif self.state == 'PDICOM':
			if cmd not in ('DR TDI', 'DR TDO'):
				return
			if cmd == 'DR TDI':
				self.pdi.handleInput(val)
			else:
				self.putx([A.JTAG_COMMAND, ['PDICOM']])
				self.pdi.handleOutput(val)
