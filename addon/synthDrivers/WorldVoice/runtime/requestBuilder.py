"""Build one complete request from normalized, engine-independent commands."""

from collections.abc import Callable, Iterable

from .models import Pause, SelectVoice
from .scheduler import InvalidRequestState, RequestState, TaskManager
from .session import PlaybackPort


def queue_speech_sequence(
    task_manager: TaskManager,
    speech_sequence: Iterable[object],
    default_voice_key: str,
    resolve: Callable[[str], PlaybackPort | None],
) -> bool:
    try:
        request = task_manager.new_request()
    except InvalidRequestState:
        return False

    voice_key = default_voice_key
    chunks = []

    def flush():
        if chunks:
            try:
                task_manager.append_speech(request, playback, voice_key, tuple(chunks))
            except InvalidRequestState:
                return False
            chunks.clear()
        return True

    try:
        playback = resolve(voice_key)
        for command in speech_sequence:
            # Selection must remain live even while the current voice is absent.
            if isinstance(command, SelectVoice):
                if not flush():
                    return False
                voice_key = command.voice_key
                playback = resolve(voice_key)
            elif playback is None:
                continue
            elif isinstance(command, Pause):
                if not flush():
                    return False
                try:
                    task_manager.append_break(request, command.seconds)
                except InvalidRequestState:
                    return False
            else:
                chunks.append(command)
        if not flush():
            return False
        return task_manager.submit_request(request)
    except Exception as error:
        # Cancellation owns its terminal state and Future cleanup.
        if request.state is RequestState.CANCELLED:
            return False
        task_manager.abort_request(request, error)
        raise
