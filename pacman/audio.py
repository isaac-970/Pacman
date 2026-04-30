from __future__ import annotations

import math
from array import array

import pygame


class AudioManager:
    def __init__(self, volume: float = 0.5) -> None:
        self.available = False
        self.sound_effects: dict[str, pygame.mixer.Sound] = {}
        self.music: pygame.mixer.Sound | None = None
        self.music_channel: pygame.mixer.Channel | None = None
        self.effects_channel: pygame.mixer.Channel | None = None
        self.volume = max(0.0, min(1.0, volume))
        self.error_message = ""

        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        except pygame.error as exc:
            self.error_message = f"Audio unavailable: {exc}"
            return

        self.available = True
        self.music_channel = pygame.mixer.Channel(0)
        self.effects_channel = pygame.mixer.Channel(1)
        self.sound_effects = {
            "dot": self._create_tone(880, 0.05, 0.18),
            "pellet": self._create_tone(660, 0.11, 0.25),
            "fruit": self._create_tone(990, 0.16, 0.28),
            "ghost": self._create_tone(330, 0.2, 0.3),
            "lose_life": self._create_tone(220, 0.35, 0.32),
            "menu": self._create_tone(740, 0.06, 0.15),
        }
        self.music = self._create_theme()
        self.apply_volume(self.volume)

    def _create_tone(self, frequency: float, duration_seconds: float, amplitude: float) -> pygame.mixer.Sound:
        sample_rate = 22050
        sample_count = max(1, int(sample_rate * duration_seconds))
        samples = array("h")
        fade = max(1, sample_count // 12)

        for index in range(sample_count):
            envelope = 1.0
            if index < fade:
                envelope = index / fade
            elif index > sample_count - fade:
                envelope = (sample_count - index) / fade

            sample = amplitude * envelope * math.sin(2.0 * math.pi * frequency * index / sample_rate)
            samples.append(int(max(-1.0, min(1.0, sample)) * 32767))

        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _create_theme(self) -> pygame.mixer.Sound:
        sample_rate = 22050
        sequence = [(440, 0.12), (554, 0.12), (659, 0.12), (880, 0.18), (659, 0.12), (554, 0.12), (440, 0.18)]
        samples = array("h")

        for frequency, duration in sequence:
            tone = self._create_tone(frequency, duration, 0.12)
            tone_samples = array("h")
            tone_samples.frombytes(tone.get_raw())
            samples.extend(tone_samples)

        return pygame.mixer.Sound(buffer=samples.tobytes())

    def apply_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if not self.available:
            return

        music_volume = self.volume * 0.35
        effects_volume = self.volume

        if self.music is not None:
            self.music.set_volume(music_volume)

        for sound in self.sound_effects.values():
            sound.set_volume(effects_volume)

    def start_music(self) -> None:
        if not self.available or self.music_channel is None or self.music is None:
            return
        if not self.music_channel.get_busy():
            self.music_channel.play(self.music, loops=-1)

    def play(self, effect_name: str) -> None:
        if not self.available or self.effects_channel is None:
            return
        sound = self.sound_effects.get(effect_name)
        if sound is not None:
            self.effects_channel.play(sound)
