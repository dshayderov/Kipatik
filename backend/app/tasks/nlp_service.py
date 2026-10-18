from typing import List, Dict
import re

class NLPEngine:
    @staticmethod
    async def analyze_task(title: str, description: str) -> Dict:
        """
        Анализирует заголовок и описание задачи.
        Возвращает: предполагаемую категорию, приоритет и список подзадач.
        """
        text = (title + " " + (description or "")).lower()
        
        # 1. Определение категории (Classification)
        category = "feature"
        if any(word in text for word in ["bug", "error", "fix", "issue", "ошибка"]):
            category = "bug"
        elif any(word in text for word in ["refactor", "clean", "improve", "рефакторинг"]):
            category = "refactor"
        elif any(word in text for word in ["research", "investigate", "study"]):
            category = "research"

        # 2. Определение приоритета (Priority Detection)
        priority = 1 # Low
        if any(word in text for word in ["urgent", "critical", "blocker", "fast", "срочно"]):
            priority = 3 # High
        elif any(word in text for word in ["important", "need", "should"]):
            priority = 2 # Mid

        # 3. Выделение подзадач (Subtask Extraction)
        # Ищем списки типа "- делать то", "1. делать это"
        subtasks = re.findall(r'(?:^|\n)(?:-|\*|\d+\.)\s*(.+)', description or "")
        
        # Если в описании нет списка, пробуем выделить по глаголам (упрощенно)
        if not subtasks:
            # Пример: "Нужно создать базу данных и написать API" -> ["Создать базу данных", "Написать API"]
            actions = re.split(r' and | и |, ', title)
            if len(actions) > 1:
                subtasks = [a.strip().capitalize() for a in actions]

        return {
            "suggested_category": category,
            "suggested_priority": priority,
            "subtasks": subtasks[:5] # Ограничим до 5
        }

nlp_engine = NLPEngine()
