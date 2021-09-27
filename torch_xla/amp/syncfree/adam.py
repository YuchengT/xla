import math
import torch
import torch.optim._functional as F
from torch.optim.optimizer import Optimizer, required
from torch import Tensor
import torch_xla
from typing import List, Optional


class Adam(Optimizer):
    r"""Implements Adam algorithm.

    It has been proposed in `Adam: A Method for Stochastic Optimization`_.
    The implementation of the L2 penalty follows changes proposed in
    `Decoupled Weight Decay Regularization`_.

    Args:
        params (iterable): iterable of parameters to optimize or dicts defining
            parameter groups
        lr (float, optional): learning rate (default: 1e-3)
        betas (Tuple[float, float], optional): coefficients used for computing
            running averages of gradient and its square (default: (0.9, 0.999))
        eps (float, optional): term added to the denominator to improve
            numerical stability (default: 1e-8)
        weight_decay (float, optional): weight decay (L2 penalty) (default: 0)
        amsgrad (boolean, optional): whether to use the AMSGrad variant of this
            algorithm from the paper `On the Convergence of Adam and Beyond`_
            (default: False)

    .. _Adam\: A Method for Stochastic Optimization:
        https://arxiv.org/abs/1412.6980
    .. _Decoupled Weight Decay Regularization:
        https://arxiv.org/abs/1711.05101
    .. _On the Convergence of Adam and Beyond:
        https://openreview.net/forum?id=ryQu7f-RZ
    """

    def __init__(self, params, lr=1e-3, betas=(0.9, 0.999), eps=1e-8,
                 weight_decay=0, amsgrad=False):
        if not 0.0 <= lr:
            raise ValueError("Invalid learning rate: {}".format(lr))
        if not 0.0 <= eps:
            raise ValueError("Invalid epsilon value: {}".format(eps))
        if not 0.0 <= betas[0] < 1.0:
            raise ValueError("Invalid beta parameter at index 0: {}".format(betas[0]))
        if not 0.0 <= betas[1] < 1.0:
            raise ValueError("Invalid beta parameter at index 1: {}".format(betas[1]))
        if not 0.0 <= weight_decay:
            raise ValueError("Invalid weight_decay value: {}".format(weight_decay))
        defaults = dict(lr=lr, betas=betas, eps=eps,
                        weight_decay=weight_decay, amsgrad=amsgrad)
        super(Adam, self).__init__(params, defaults)

    def __setstate__(self, state):
        super(Adam, self).__setstate__(state)
        for group in self.param_groups:
            group.setdefault('amsgrad', False)

    @torch.no_grad()
    def step(self, closure=None, found_inf: Tensor = None):
        """Performs a single optimization step.

        Args:
            closure (callable, optional): A closure that reevaluates the model
                and returns the loss.
        """
        if len(found_inf.shape) != 0:
            raise ValueError("The found_inf tensor has to be scalar type")
        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()
        for group in self.param_groups:
            params_with_grad = []
            grads = []
            exp_avgs = []
            exp_avg_sqs = []
            max_exp_avg_sqs = []
            state_steps = []
            beta1, beta2 = group['betas']

            for p in group['params']:
                if p.grad is not None:
                    params_with_grad.append(p)
                    if p.grad.is_sparse:
                        raise RuntimeError('Adam does not support sparse gradients, please consider SparseAdam instead')
                    grads.append(p.grad)

                    state = self.state[p]
                    # if 'step' not in state:
                    #     state['step'] = torch.zeros_like(found_inf)                    
                    # state_steps.append(state['step'])
                    # Lazy state initialization

                    if len(state) == 0:
                        # state['step'] = torch.zeros_like(found_inf) # Changed 
                        state['step'] = 0
                        # Exponential moving average of gradient values
                        state['exp_avg'] = torch.zeros_like(p, memory_format=torch.preserve_format)
                        # Exponential moving average of squared gradient values
                        state['exp_avg_sq'] = torch.zeros_like(p, memory_format=torch.preserve_format)
                        if group['amsgrad']:
                            # Maintains max of all exp. moving avg. of sq. grad. values
                            state['max_exp_avg_sq'] = torch.zeros_like(p, memory_format=torch.preserve_format)

                    exp_avgs.append(state['exp_avg'])
                    exp_avg_sqs.append(state['exp_avg_sq'])

                    if group['amsgrad']:
                        max_exp_avg_sqs.append(state['max_exp_avg_sq'])

                    # update the steps for each param group update
                    if not found_inf:
                        state['step'] += 1
                    # record the step after step update
                    state_steps.append(state['step'])

            # self.adam_step_cpp(params_with_grad,
            #        grads,
            #        exp_avgs,
            #        exp_avg_sqs,
            #        max_exp_avg_sqs,
            #        state_steps,
            #        amsgrad=group['amsgrad'],
            #        beta1=beta1,
            #        beta2=beta2,
            #        lr=group['lr'],
            #        weight_decay=group['weight_decay'],
            #        eps=group['eps'],
            #        found_inf=found_inf)
            self.adam_step_py(params_with_grad,
                   grads,
                   exp_avgs,
                   exp_avg_sqs,
                   max_exp_avg_sqs,
                   state_steps,
                   amsgrad=group['amsgrad'],
                   beta1=beta1,
                   beta2=beta2,
                   lr=group['lr'],
                   weight_decay=group['weight_decay'],
                   eps=group['eps'],
                   found_inf=found_inf)


        return loss


    def adam_step_cpp(self, params: List[Tensor], grads: List[Tensor],
                    exp_avgs: List[Tensor], exp_avg_sqs: List[Tensor], 
                    max_exp_avg_sqs: List[Tensor], state_steps: List[int],
                    amsgrad: bool, beta1: float, beta2: float, lr: float, 
                    weight_decay: float, eps: float, found_inf: Tensor):
        r"""Functional API that performs SGD algorithm computation.

            See :class:`~torch.optim.SGD` for details.
            """

        for i, param in enumerate(params):
            grad = grads[i]
            exp_avg = exp_avgs[i]
            exp_avg_sq = exp_avg_sqs[i]
            step = state_steps[i]
            max_exp_avg_sq = max_exp_avg_sqs[i] 

            torch_xla._XLAC._xla_adam_optimizer_step(found_inf, step, param, grad,
                                                    exp_avg, exp_avg_sq, max_exp_avg_sq, 
                                                    amsgrad, beta1, beta2, lr, weight_decay, eps)

    def adam_step_py(self, params: List[Tensor], grads: List[Tensor],
                    exp_avgs: List[Optional[Tensor]], exp_avg_sqs: List[Tensor], 
                    max_exp_avg_sqs: List[Tensor], state_steps: List[int],
                    amsgrad: bool, beta1: float, beta2: float, lr: float, 
                    weight_decay: float, eps: float, found_inf: Tensor):

        for i, param in enumerate(params):
            import pdb;pdb.set_trace()
            grad = grads[i]
            exp_avg = exp_avgs[i]
            exp_avg_sq = exp_avg_sqs[i]
            step = state_steps[i]

            bias_correction1 = 1 - beta1 ** step
            bias_correction2 = 1 - beta2 ** step

            if weight_decay != 0:
                grad = torch.where(found_inf.to(torch.bool), grad, grad.add(param, alpha=weight_decay))

            # Decay the first and second moment running average coefficient
            if not found_inf:
                exp_avg.mul_(beta1).add_(grad, alpha=1 - beta1)
            if not found_inf:
                exp_avg_sq.mul_(beta2).addcmul_(grad, grad.conj(), value=1 - beta2)
            if amsgrad:
                # Maintains the maximum of all 2nd moment running avg. till now
                torch.maximum(max_exp_avg_sqs[i], exp_avg_sq, out=max_exp_avg_sqs[i])
                # Use the max. for normalizing running avg. of gradient
                if step:
                    denom = (max_exp_avg_sqs[i].sqrt() / math.sqrt(bias_correction2)).add_(eps)
                else:
                    denom = torch.ones_like(max_exp_avg_sqs[i])
            else:
                if step:
                    denom = (exp_avg_sq.sqrt() / math.sqrt(bias_correction2)).add_(eps)
                else:
                    denom = torch.ones_like(exp_avg_sq)

            if step:
                step_size = lr / bias_correction1
            else:
                step_size = 0
            
            if not found_inf:
                param.addcdiv_(exp_avg, denom, value=-step_size)
            else:
                param.add_(torch.zeros_like(exp_avg))
