"""Widget that renders a list of questions and collects answers."""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QRadioButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..core.categories import Question


class QuestionForm(QScrollArea):
    """Scrollable form of radio-button (single) and checkbox (multi) questions."""

    changed = Signal()

    def __init__(self, questions: Sequence[Question] = (), parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self.setWidget(self._inner)
        self._controls: dict[str, tuple[Question, list]] = {}
        self.set_questions(questions)

    def set_questions(self, questions: Sequence[Question], answers: dict[str, Any] | None = None) -> None:
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._controls.clear()
        for n, q in enumerate(questions, 1):
            box = QGroupBox(f"{n}. {q.text}")
            grid = QGridLayout(box)
            cols = 3 if len(q.options) > 6 else 2
            buttons = []
            group = None
            if not q.multi:
                group = QButtonGroup(box)
                group.setExclusive(True)
            for i, opt in enumerate(q.options):
                b = QCheckBox(opt.label) if q.multi else QRadioButton(opt.label)
                tip = ", ".join(k.replace("_", " ") for k in opt.traits)
                if tip:
                    b.setToolTip(f"Suggests: {tip}")
                if group is not None:
                    group.addButton(b)
                b.toggled.connect(lambda *_: self.changed.emit())
                grid.addWidget(b, i // cols, i % cols)
                buttons.append(b)
            self._controls[q.id] = (q, buttons)
            box._group = group  # keep alive
            self._layout.addWidget(box)
        self._layout.addStretch(1)
        if answers:
            self.set_answers(answers)

    def answers(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for qid, (q, buttons) in self._controls.items():
            chosen = [b.text() for b in buttons if b.isChecked()]
            if q.multi:
                if chosen:
                    out[qid] = chosen
            elif chosen:
                out[qid] = chosen[0]
        return out

    def set_answers(self, answers: dict[str, Any]) -> None:
        for qid, (q, buttons) in self._controls.items():
            ans = answers.get(qid)
            chosen = ans if isinstance(ans, list) else [ans] if ans else []
            for b in buttons:
                b.blockSignals(True)
                b.setChecked(b.text() in chosen)
                b.blockSignals(False)
        self.changed.emit()

    def unanswered(self) -> list[str]:
        ans = self.answers()
        return [q.text for qid, (q, _) in self._controls.items() if not q.multi and qid not in ans]
