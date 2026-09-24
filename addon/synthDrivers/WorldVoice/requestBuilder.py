from speech.commands import BreakCommand

from .driver import Voice


def queue_speech_sequence(task_manager, speech_sequence, default_voice, ready_engines):
	request = task_manager.new_request()
	voice, chunks = default_voice, []
	for command in speech_sequence:
		if voice.engine not in ready_engines:
			continue
		if isinstance(command, Voice):
			if chunks:
				voice.speak(chunks, request)
			chunks = []
			voice = command
		elif isinstance(command, BreakCommand):
			if chunks:
				voice.speak(chunks, request)
			chunks = []
			voice.breaks(command.time / 1000, request)
		else:
			chunks.append(command)
	if chunks and voice.engine in ready_engines:
		voice.speak(chunks, request)
	return task_manager.submit_request(request)
