"""
Mamdani Fuzzy Inference System for DUO-GAIT Exercise Classification

三维分类系统：
  Dim 1: Exercise Load (低/中/高/过高)
  Dim 2: Fatigue Level (无/轻/中/重)
  Dim 3: Movement Quality (良好/降低/差)

基于模糊逻辑融合多个生理指标。
"""

import numpy as np
from typing import Dict, Tuple


class FuzzyExerciseClassifier:
    """
    简化的 Mamdani 模糊推理系统分类器 (直接隶属度计算)
    
    输入 (Antecedents):
      - hr_mean: [40, 180] bpm，基于 %MHR
      - step_var: [10, 150] ms，步伐变异
      - hr_recovery: [0, 50] bpm/min，恢复速率
      - stride_length: [0.1, 1.8] m
      - rpe_score: [6, 20] Borg Scale
    
    输出 (Consequents):
      - exercise_load: [0, 4] → low(0-1), moderate(1-2), high(2-3), excessive(3-4)
      - fatigue_level: [0, 4] → none(0-1), mild(1-2), moderate(2-3), severe(3-4)
      - movement_quality: [0, 2] → good(0-0.67), degraded(0.67-1.33), poor(1.33-2)
    """
    
    def __init__(self, age=70):
        """
        初始化模糊分类器
        
        Args:
            age: 受试者年龄（用于计算 MHR）
        """
        self.age = age
        self.mhr = 220 - age
    
    # ============================================================
    # 隶属度函数 (Membership Functions)
    # ============================================================
    
    @staticmethod
    def _triangular_mf(x, a, b, c):
        """三角形隶属函数"""
        if x <= a or x >= c:
            return 0.0
        elif a < x <= b:
            return (x - a) / (b - a)
        else:
            return (c - x) / (c - b)
    
    @staticmethod
    def _trapezoidal_mf(x, a, b, c, d):
        """梯形隶属函数"""
        if x <= a or x >= d:
            return 0.0
        elif a < x <= b:
            return (x - a) / (b - a)
        elif b < x < c:
            return 1.0
        else:
            return (d - x) / (d - c)
    
    def _get_hr_membership(self, hr_mean):
        """HR 隶属度计算"""
        hr_low = self._trapezoidal_mf(hr_mean, 40, 40, int(0.5*self.mhr), int(0.65*self.mhr))
        hr_moderate = self._triangular_mf(hr_mean, int(0.55*self.mhr), int(0.7*self.mhr), int(0.85*self.mhr))
        hr_high = self._triangular_mf(hr_mean, int(0.75*self.mhr), int(0.9*self.mhr), int(1.0*self.mhr))
        hr_excessive = self._trapezoidal_mf(hr_mean, int(0.95*self.mhr), int(1.0*self.mhr), 180, 180)
        
        return {
            'low': hr_low, 'moderate': hr_moderate, 'high': hr_high, 'excessive': hr_excessive
        }
    
    def _get_step_var_membership(self, step_var):
        """步伐变异隶属度"""
        stable = self._trapezoidal_mf(step_var, 10, 10, 20, 35)
        unstable = self._triangular_mf(step_var, 25, 45, 65)
        at_risk = self._trapezoidal_mf(step_var, 55, 70, 150, 150)
        
        return {'stable': stable, 'unstable': unstable, 'at_risk': at_risk}
    
    def _get_hr_recovery_membership(self, hr_recovery):
        """心率恢复隶属度"""
        poor = self._trapezoidal_mf(hr_recovery, 0, 0, 8, 15)
        fair = self._triangular_mf(hr_recovery, 10, 16, 25)
        good = self._trapezoidal_mf(hr_recovery, 20, 30, 50, 50)
        
        return {'poor': poor, 'fair': fair, 'good': good}
    
    def _get_stride_length_membership(self, stride_length):
        """步长隶属度"""
        short = self._trapezoidal_mf(stride_length, 0.1, 0.1, 0.35, 0.45)
        normal = self._trapezoidal_mf(stride_length, 0.38, 0.50, 1.8, 1.8)
        
        return {'short': short, 'normal': normal}
    
    def _get_rpe_membership(self, rpe_score):
        """RPE 隶属度"""
        light = self._trapezoidal_mf(rpe_score, 6, 6, 7, 8)
        moderate = self._triangular_mf(rpe_score, 7, 8.5, 10)
        heavy = self._trapezoidal_mf(rpe_score, 9, 11, 20, 20)
        
        return {'light': light, 'moderate': moderate, 'heavy': heavy}
    
    def classify(self, hr_mean, step_var, hr_recovery, stride_length, rpe_score=12):
        """
        对单个 30s 窗口进行分类
        
        Args:
            hr_mean (float): 平均心率 (bpm)
            step_var (float): 步幅变异 (ms，ISI 标准差)
            hr_recovery (float): 心率恢复速率 (bpm/min)
            stride_length (float): 平均步长 (m)
            rpe_score (float): 主观感觉费力程度 (Borg 6-20)，默认 12（中等）
        
        Returns:
            dict: {
                'exercise_load': (value, category),
                'fatigue_level': (value, category),
                'movement_quality': (value, category),
                'confidence': float (0-1, 基于输出隶属度)
            }
        """
        
        # 输入范围检查和裁剪
        hr_mean = np.clip(hr_mean, 40, 180)
        step_var = np.clip(step_var, 10, 150)
        hr_recovery = np.clip(hr_recovery, 0, 50)
        stride_length = np.clip(stride_length, 0.1, 1.8)
        rpe_score = np.clip(rpe_score, 6, 20)
        
        # 计算输入隶属度
        hr_mem = self._get_hr_membership(hr_mean)
        step_mem = self._get_step_var_membership(step_var)
        recov_mem = self._get_hr_recovery_membership(hr_recovery)
        stride_mem = self._get_stride_length_membership(stride_length)
        rpe_mem = self._get_rpe_membership(rpe_score)
        
        # ============================================================
        # 规则评估和输出推论
        # ============================================================
        
        # Dim 1: 运动负荷规则
        load_low = hr_mem['low']
        load_moderate = hr_mem['moderate']
        load_high = hr_mem['high']
        load_excessive = hr_mem['excessive']
        
        # RPE 冲突：高 RPE 提升负荷等级
        if rpe_mem['heavy'] > 0.5:
            if hr_mem['moderate'] > 0.3:
                load_high = max(load_high, rpe_mem['heavy'] * 0.9)
            if hr_mem['high'] > 0.3:
                load_excessive = max(load_excessive, rpe_mem['heavy'] * 0.85)
        
        # 计算负荷值（0-4）
        load_value = (
            load_low * 0.5 +
            load_moderate * 1.5 +
            load_high * 3.0 +
            load_excessive * 3.8
        ) / (load_low + load_moderate + load_high + load_excessive + 1e-6)
        
        # Dim 2: 疲劳等级规则
        fatigue_none = step_mem['stable'] * recov_mem['good']
        fatigue_mild = (
            (step_mem['unstable'] * recov_mem['good']) +
            (step_mem['stable'] * recov_mem['fair'])
        ) / 2
        fatigue_moderate = (
            (step_mem['unstable'] * recov_mem['fair']) +
            (step_mem['at_risk'] * recov_mem['fair'])
        ) / 2
        fatigue_severe = (
            (step_mem['at_risk'] * recov_mem['poor']) +
            (step_mem['at_risk'] * stride_mem['short']) +
            rpe_mem['heavy']
        ) / 3
        
        # 计算疲劳值（0-4）
        fatigue_weights = (fatigue_none + fatigue_mild + fatigue_moderate + fatigue_severe + 1e-6)
        fatigue_value = (
            fatigue_none * 0.5 +
            fatigue_mild * 1.5 +
            fatigue_moderate * 3.0 +
            fatigue_severe * 3.8
        ) / fatigue_weights
        
        # Dim 3: 动作质量规则
        quality_good = step_mem['stable'] * stride_mem['normal']
        quality_degraded = (
            (step_mem['unstable'] * stride_mem['normal']) +
            (step_mem['stable'] * stride_mem['short'])
        ) / 2
        quality_poor = (
            step_mem['at_risk'] +
            (stride_mem['short'] * step_mem['unstable'])
        ) / 2
        
        # 计算质量值（0-2）
        quality_weights = (quality_good + quality_degraded + quality_poor + 1e-6)
        quality_value = (
            quality_good * 0.3 +
            quality_degraded * 1.0 +
            quality_poor * 1.8
        ) / quality_weights
        
        # 映射到分类标签
        load_category = self._categorize_load(load_value)
        fatigue_category = self._categorize_fatigue(fatigue_value)
        quality_category = self._categorize_quality(quality_value)
        
        # 计算置信度
        confidence = self._calculate_confidence(hr_mean, step_var)
        
        return {
            'exercise_load': (load_value, load_category),
            'fatigue_level': (fatigue_value, fatigue_category),
            'movement_quality': (quality_value, quality_category),
            'confidence': confidence,
            'reasoning': self._generate_reasoning(
                hr_mean, step_var, hr_recovery, stride_length, rpe_score
            )
        }
    
    @staticmethod
    def _categorize_load(value):
        """将连续输出值映射到负荷分类"""
        if value < 1.0:
            return 'low'
        elif value < 2.0:
            return 'moderate'
        elif value < 3.0:
            return 'high'
        else:
            return 'excessive'
    
    @staticmethod
    def _categorize_fatigue(value):
        """将连续输出值映射到疲劳分类"""
        if value < 1.0:
            return 'none'
        elif value < 2.0:
            return 'mild'
        elif value < 3.0:
            return 'moderate'
        else:
            return 'severe'
    
    @staticmethod
    def _categorize_quality(value):
        """将连续输出值映射到质量分类"""
        if value < 0.67:
            return 'good'
        elif value < 1.33:
            return 'degraded'
        else:
            return 'poor'
    
    def _calculate_confidence(self, hr_mean, step_var):
        """
        计算分类置信度（相对于参考范围的偏离度）
        
        - HR 在最优范围内 → 高置信度
        - 步伐变异在正常范围 → 高置信度
        """
        # HR 置信度：偏离 60-80% MHR 越远，置信度越低
        hr_optimal_low = 0.60 * self.mhr
        hr_optimal_high = 0.80 * self.mhr
        
        if hr_optimal_low <= hr_mean <= hr_optimal_high:
            hr_confidence = 1.0
        else:
            hr_distance = min(
                abs(hr_mean - hr_optimal_low),
                abs(hr_mean - hr_optimal_high)
            )
            hr_confidence = max(0.5, 1.0 - hr_distance / (0.3 * self.mhr))
        
        # 步伐置信度：<30ms 和 30-60ms 置信度高
        if step_var < 60:
            step_confidence = 1.0
        else:
            step_confidence = max(0.6, 1.0 - (step_var - 60) / 90)
        
        # 综合置信度
        return (hr_confidence + step_confidence) / 2.0
    
    def _generate_reasoning(self, hr_mean, step_var, hr_recovery, stride_length, rpe_score):
        """
        生成分类决策的理由说明
        
        Returns:
            str: 人类可读的推理过程
        """
        reasons = []
        
        # HR 分析
        hr_pct = (hr_mean / self.mhr) * 100
        if hr_pct < 50:
            reasons.append(f"HR: {hr_mean:.0f} bpm ({hr_pct:.0f}% MHR) - 低强度")
        elif hr_pct < 70:
            reasons.append(f"HR: {hr_mean:.0f} bpm ({hr_pct:.0f}% MHR) - 中等强度")
        elif hr_pct < 90:
            reasons.append(f"HR: {hr_mean:.0f} bpm ({hr_pct:.0f}% MHR) - 高强度")
        else:
            reasons.append(f"HR: {hr_mean:.0f} bpm ({hr_pct:.0f}% MHR) - 过高强度 ⚠️")
        
        # 步伐变异分析
        if step_var < 30:
            reasons.append(f"Step Var: {step_var:.1f} ms - 步伐稳定")
        elif step_var < 60:
            reasons.append(f"Step Var: {step_var:.1f} ms - 步伐有变异")
        else:
            reasons.append(f"Step Var: {step_var:.1f} ms - 步伐显著变异 ⚠️")
        
        # 恢复速率分析
        if hr_recovery < 12:
            reasons.append(f"HR Recovery: {hr_recovery:.1f} bpm/min - 恢复差 ⚠️")
        elif hr_recovery < 20:
            reasons.append(f"HR Recovery: {hr_recovery:.1f} bpm/min - 恢复一般")
        else:
            reasons.append(f"HR Recovery: {hr_recovery:.1f} bpm/min - 恢复良好")
        
        # 步长分析
        if stride_length < 0.40:
            reasons.append(f"Stride: {stride_length:.2f} m - 步长短 ⚠️")
        else:
            reasons.append(f"Stride: {stride_length:.2f} m - 步长正常")
        
        # RPE 分析
        if rpe_score < 7:
            reasons.append(f"RPE: {rpe_score:.0f} - 感觉轻松")
        elif rpe_score < 9:
            reasons.append(f"RPE: {rpe_score:.0f} - 感觉适中")
        else:
            reasons.append(f"RPE: {rpe_score:.0f} - 感觉费力 ⚠️")
        
        return " | ".join(reasons)


# ============================================================
# 工具函数
# ============================================================

def create_classifier(age):
    """创建新的模糊分类器"""
    return FuzzyExerciseClassifier(age=age)


def classify_batch(classifier, windows_data):
    """
    对一批 30s 窗口数据进行分类
    
    Args:
        classifier: FuzzyExerciseClassifier 实例
        windows_data (list): 每个窗口的特征字典列表
            [
                {
                    'hr_mean': float,
                    'step_var': float,
                    'hr_recovery': float,
                    'stride_length': float,
                    'rpe_score': float,
                    'timestamp': str (可选)
                },
                ...
            ]
    
    Returns:
        list: 分类结果列表
            [
                {
                    'timestamp': str,
                    'exercise_load': (value, category),
                    'fatigue_level': (value, category),
                    'movement_quality': (value, category),
                    'confidence': float,
                    'reasoning': str
                },
                ...
            ]
    """
    results = []
    
    for window in windows_data:
        rpe = window.get('rpe_score', 12)  # 默认中等 RPE
        
        result = classifier.classify(
            hr_mean=window['hr_mean'],
            step_var=window['step_var'],
            hr_recovery=window['hr_recovery'],
            stride_length=window['stride_length'],
            rpe_score=rpe
        )
        
        if 'timestamp' in window:
            result['timestamp'] = window['timestamp']
        
        results.append(result)
    
    return results


if __name__ == '__main__':
    # 示例使用
    print("="*60)
    print("模糊逻辑分类系统 - 测试")
    print("="*60)
    
    # 创建 70 岁受试者的分类器 (MHR = 150 bpm)
    classifier = FuzzyExerciseClassifier(age=70)
    
    # 测试场景 1：正常步行
    print("\n[情景 1] 正常步行")
    result = classifier.classify(
        hr_mean=100,      # 67% MHR，中等
        step_var=25,      # 稳定
        hr_recovery=18,   # 一般恢复
        stride_length=0.55,  # 正常步长
        rpe_score=12      # 中等费力
    )
    print(f"  负荷: {result['exercise_load']}")
    print(f"  疲劳: {result['fatigue_level']}")
    print(f"  质量: {result['movement_quality']}")
    print(f"  置信度: {result['confidence']:.2f}")
    print(f"  推理: {result['reasoning']}")
    
    # 测试场景 2：高强度 + 疲劳
    print("\n[情景 2] 高强度 + 疲劳迹象")
    result = classifier.classify(
        hr_mean=135,      # 90% MHR，高度
        step_var=75,      # 显著变异
        hr_recovery=8,    # 恢复差
        stride_length=0.35,  # 步长短
        rpe_score=16      # 非常费力
    )
    print(f"  负荷: {result['exercise_load']}")
    print(f"  疲劳: {result['fatigue_level']}")
    print(f"  质量: {result['movement_quality']}")
    print(f"  置信度: {result['confidence']:.2f}")
    print(f"  推理: {result['reasoning']}")
    
    # 测试场景 3：危险 HR
    print("\n[情景 3] HR 过高警告")
    result = classifier.classify(
        hr_mean=160,      # 107% MHR，过高！
        step_var=95,      # 严重变异
        hr_recovery=3,    # 极差恢复
        stride_length=0.25,  # 严重缩短
        rpe_score=18      # 极度费力
    )
    print(f"  负荷: {result['exercise_load']}")
    print(f"  疲劳: {result['fatigue_level']}")
    print(f"  质量: {result['movement_quality']}")
    print(f"  置信度: {result['confidence']:.2f}")
    print(f"  推理: {result['reasoning']}")
    print(f"  ⚠️ 警告: HR 超过 {classifier.mhr} (MHR)")
