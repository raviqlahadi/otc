import time
from typing import Optional

from models.assessment import AnswerResult, BKTParams, Question, StudentMastery
from repositories.interactions import InteractionRepository
from repositories.mastery import MasteryRepository
from repositories.progress import ProgressRepository


class OptionTracingEngine:
    """BKT-based assessment engine. Pure logic + repository delegation."""

    def __init__(self, mastery_repo: MasteryRepository, interaction_repo: InteractionRepository,
                 progress_repo: ProgressRepository, bkt_params: dict[str, BKTParams]):
        self._mastery_repo = mastery_repo
        self._interaction_repo = interaction_repo
        self._progress_repo = progress_repo
        self._params = bkt_params

    async def initialize_student(self, student_id: str) -> None:
        await self._mastery_repo.initialize_student(student_id, self._params)

    def compute_mastery_update(self, mastery: StudentMastery, correct: bool, params: BKTParams) -> StudentMastery:
        """Pure BKT posterior update. No side effects."""
        if correct:
            p_obs_given_mastery = 1 - params.p_slip
            p_obs_given_not = params.p_guess
        else:
            p_obs_given_mastery = params.p_slip
            p_obs_given_not = 1 - params.p_guess

        p_obs = p_obs_given_mastery * mastery.p_mastery + p_obs_given_not * (1 - mastery.p_mastery)
        if p_obs == 0:
            posterior = mastery.p_mastery
        else:
            posterior = (p_obs_given_mastery * mastery.p_mastery) / p_obs

        mastery.p_mastery = posterior + mastery.p_transition * (1 - posterior)
        mastery.p_mastery = max(0.0, min(1.0, mastery.p_mastery))
        mastery.last_updated = time.time()
        return mastery

    async def process_answer(self, student_id: str, question: Question, selected_option: str,
                             attempt_number: int, session_id: str) -> AnswerResult:
        """Process answer: check correctness, log, update mastery."""
        is_correct = selected_option.upper() == question.correct_option
        misconception_id = None if is_correct else question.distractor_map.get(selected_option.upper())

        await self._interaction_repo.log(
            student_id, question.id, session_id, attempt_number, selected_option, is_correct, misconception_id
        )

        params = self._params.get(question.kc_id, BKTParams(0.3, 0.25, 0.1, 0.1))
        mastery = await self._mastery_repo.load(student_id, question.kc_id, params)
        mastery = self.compute_mastery_update(mastery, is_correct, params)

        if misconception_id:
            await self._mastery_repo.update_misconception_prob(student_id, question.kc_id, misconception_id)

        await self._mastery_repo.save(mastery)
        return AnswerResult(is_correct=is_correct, misconception_id=misconception_id,
                            attempt_number=attempt_number, updated_mastery=mastery)

    def classify_misconception_pattern(self, selected_options: list[dict]) -> tuple[str, str]:
        """Classify misconception pattern from attempt history."""
        counts: dict[str, int] = {}
        last_misconception: Optional[str] = None
        for entry in selected_options:
            m_id = entry.get("misconception_id")
            if m_id:
                counts[m_id] = counts.get(m_id, 0) + 1
                last_misconception = m_id

        if not counts:
            return ("unknown", "varied")

        max_count = max(counts.values())
        pattern = "consistent" if max_count >= 2 else "varied"
        dominant_candidates = [m for m, c in counts.items() if c == max_count]

        if len(dominant_candidates) > 1:
            dominant = last_misconception or dominant_candidates[0]
        else:
            dominant = dominant_candidates[0]

        return (dominant, pattern)

    async def get_next_kc(self, student_id: str, current_kc_id: str) -> Optional[str]:
        return await self._progress_repo.get_next_kc(student_id, current_kc_id)
