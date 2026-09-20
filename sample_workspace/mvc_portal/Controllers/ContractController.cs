using System;
using System.Web.Mvc;

namespace SampleMvcPortal.Controllers
{
    [Authorize]
    public class ContractController : Controller
    {
        public ActionResult Index()
        {
            return PartialView("/Views/Contract/Index.cshtml");
        }

        public ActionResult Sign(Guid id)
        {
            return PartialView("/Views/Contract/Sign.cshtml");
        }

        [HttpPost]
        public ActionResult GetContractSignContext(Guid contractID)
        {
            return Json(new { ok = true });
        }
    }
}
